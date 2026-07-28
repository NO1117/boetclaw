"""Voice STT/TTS production tests with fake speech provider."""

from __future__ import annotations

import io
import struct
import wave

import httpx
import pytest
from fastapi import FastAPI

from app.providers.speech.fake import FakeSpeechProvider
from app.providers.speech.manager import speech_provider_manager
from app.services.voice.rate_limiter import voice_rate_limiter
from app.services.voice.temp_store import VoiceTempStore


def _make_wav_bytes(duration_seconds: float = 0.2, sample_rate: int = 8000) -> bytes:
    frames = max(1, int(sample_rate * duration_seconds))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(struct.pack("<h", 0) * frames)
    return buf.getvalue()


@pytest.fixture
def voice_api(tmp_path, monkeypatch):
    from app.api.routes import voice as voice_routes
    from app.core.config import settings

    fake = FakeSpeechProvider(configured=True, stt_text="hello world", tts_payload=b"FAKE-MP3-BYTES")
    monkeypatch.setattr(settings, "speech_provider", "fake")
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    monkeypatch.setattr(settings, "speech_max_upload_bytes", 1024 * 1024)
    monkeypatch.setattr(settings, "speech_max_duration_seconds", 30)
    monkeypatch.setattr(settings, "speech_max_text_chars", 256)
    monkeypatch.setattr(settings, "speech_rate_limit_per_minute", 0)
    speech_provider_manager.register(fake)
    voice_rate_limiter.reset()
    temp_root = tmp_path / "voice_temp"
    store = VoiceTempStore(temp_root)
    monkeypatch.setattr("app.services.voice.service.voice_temp_store", store)
    app = FastAPI()
    app.include_router(voice_routes.router, prefix="/api/v1")
    return app, fake, store


@pytest.mark.asyncio
async def test_capabilities_with_fake_provider(voice_api):
    app, _, _ = voice_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/voice/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "fake"
    assert body["stt"]["status"] == "configured"
    assert body["tts"]["status"] == "configured"
    assert "webm" in body["stt"]["formats"]


@pytest.mark.asyncio
async def test_transcription_success_and_cleanup(voice_api):
    app, fake, store = voice_api
    payload = _make_wav_bytes()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("sample.wav", payload, "audio/wav")}
        resp = await client.post("/api/v1/voice/transcriptions", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "hello world"
    assert body["provider"] == "fake"
    assert body["trace_id"]
    assert fake.transcribe_calls
    assert list(store.root.glob("*")) == []


@pytest.mark.asyncio
async def test_transcription_rejects_fake_mime(voice_api):
    app, fake, _ = voice_api
    payload = b"not-audio-content"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("sample.wav", payload, "audio/wav")}
        resp = await client.post("/api/v1/voice/transcriptions", files=files)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "VOICE_UNSUPPORTED_FORMAT"
    assert fake.transcribe_calls == []


@pytest.mark.asyncio
async def test_transcription_rejects_oversized(voice_api, monkeypatch):
    from app.core.config import settings

    app, fake, _ = voice_api
    monkeypatch.setattr(settings, "speech_max_upload_bytes", 128)
    payload = _make_wav_bytes(duration_seconds=1.0)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("sample.wav", payload, "audio/wav")}
        resp = await client.post("/api/v1/voice/transcriptions", files=files)
    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "VOICE_FILE_TOO_LARGE"
    assert fake.transcribe_calls == []


@pytest.mark.asyncio
async def test_transcription_unconfigured(voice_api):
    app, fake, _ = voice_api
    fake._configured = False
    payload = _make_wav_bytes()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("sample.wav", payload, "audio/wav")}
        resp = await client.post("/api/v1/voice/transcriptions", files=files)
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "VOICE_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_speech_streaming_response(voice_api):
    app, fake, _ = voice_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/voice/speech",
            json={"text": "测试朗读", "format": "mp3"},
        )
    assert resp.status_code == 200
    assert resp.headers["cache-control"].startswith("no-store")
    assert resp.headers["x-voice-trace-id"]
    assert resp.content == b"FAKE-MP3-BYTES"
    assert fake.synthesize_calls
    assert fake.synthesize_calls[0]["text_len"] == len("测试朗读")


@pytest.mark.asyncio
async def test_speech_rejects_empty_text(voice_api):
    app, _, _ = voice_api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/voice/speech", json={"text": "   "})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "VOICE_UNSUPPORTED_FORMAT"


@pytest.mark.asyncio
async def test_speech_rejects_long_text(voice_api, monkeypatch):
    from app.core.config import settings

    app, _, _ = voice_api
    monkeypatch.setattr(settings, "speech_max_text_chars", 8)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/voice/speech", json={"text": "123456789"})
    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "VOICE_TEXT_TOO_LONG"


@pytest.mark.asyncio
async def test_rate_limit(voice_api, monkeypatch):
    from app.core.config import settings

    app, _, _ = voice_api
    monkeypatch.setattr(settings, "speech_rate_limit_per_minute", 1)
    voice_rate_limiter.reset()
    payload = _make_wav_bytes()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("sample.wav", payload, "audio/wav")}
        first = await client.post("/api/v1/voice/transcriptions", files=files)
        second = await client.post("/api/v1/voice/transcriptions", files=files)
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "VOICE_RATE_LIMITED"


@pytest.mark.asyncio
async def test_transcription_failure_cleans_temp(voice_api):
    app, fake, store = voice_api
    fake._fail_stt = True
    payload = _make_wav_bytes()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("sample.wav", payload, "audio/wav")}
        resp = await client.post("/api/v1/voice/transcriptions", files=files)
    assert resp.status_code == 502
    assert list(store.root.glob("*")) == []


@pytest.mark.asyncio
async def test_openai_provider_not_called_when_unconfigured(monkeypatch):
    from app.core.config import settings
    from app.providers.speech.errors import VoiceError
    from app.providers.speech.openai_compatible import OpenAICompatibleSpeechProvider

    monkeypatch.setattr(settings, "speech_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    provider = OpenAICompatibleSpeechProvider()
    assert provider.is_configured() is False
    with pytest.raises(VoiceError) as exc:
        await provider.transcribe(audio_path="x.wav", filename="x.wav", mime_type="audio/wav")
    assert exc.value.code == "VOICE_NOT_CONFIGURED"
