"""OpenAI-compatible speech STT/TTS adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from app.core.config import settings
from app.core.observability import get_logger
from app.providers.speech.base import AvailabilityState, SpeechCapabilities, SpeechProvider, TranscriptionResult
from app.providers.speech.errors import VOICE_NOT_CONFIGURED, VOICE_UNAVAILABLE, VoiceError

logger = get_logger("speech_openai")


class OpenAICompatibleSpeechProvider(SpeechProvider):
    name = "openai_compatible"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _api_key(self) -> str:
        return (settings.speech_api_key or settings.openai_api_key or "").strip()

    def _base_url(self) -> str:
        raw = (settings.speech_base_url or settings.openai_base_url or "https://api.openai.com/v1").strip()
        return raw.rstrip("/")

    def is_configured(self) -> bool:
        return bool(self._api_key())

    def _client_instance(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url(),
                timeout=httpx.Timeout(settings.speech_timeout_seconds, connect=15.0),
                headers={"Authorization": f"Bearer {self._api_key()}"},
            )
        return self._client

    async def check_availability(self) -> tuple[AvailabilityState, AvailabilityState]:
        if not self.is_configured():
            return "unconfigured", "unconfigured"
        try:
            client = self._client_instance()
            resp = await client.get("/models", params={"limit": 1})
            if resp.status_code == 401:
                return "unavailable", "unavailable"
            if resp.status_code >= 500:
                return "unknown", "unknown"
            return "configured", "configured"
        except Exception:
            return "unknown", "unknown"

    def capabilities(self) -> SpeechCapabilities:
        stt_status: AvailabilityState
        tts_status: AvailabilityState
        if not self.is_configured():
            stt_status = tts_status = "unconfigured"
        else:
            stt_status = tts_status = "configured"
        return SpeechCapabilities(
            provider=self.name,
            stt_status=stt_status,
            tts_status=tts_status,
            stt_model=settings.speech_stt_model,
            tts_model=settings.speech_tts_model,
            tts_voice=settings.speech_tts_voice,
            tts_formats=["mp3", "opus", "aac", "flac", "wav", "pcm"],
            input_formats=["webm", "ogg", "wav", "mp3", "m4a"],
            max_upload_bytes=settings.speech_max_upload_bytes,
            max_duration_seconds=settings.speech_max_duration_seconds,
            max_text_chars=settings.speech_max_text_chars,
            browser_fallback=True,
        )

    async def transcribe(
        self,
        *,
        audio_path: str,
        filename: str,
        mime_type: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        if not self.is_configured():
            raise VoiceError(VOICE_NOT_CONFIGURED, "语音服务未配置", status_code=503)
        path = Path(audio_path)
        data: dict[str, Any] = {"model": settings.speech_stt_model}
        if language:
            data["language"] = language
        try:
            client = self._client_instance()
            with path.open("rb") as handle:
                files = {"file": (filename, handle, mime_type)}
                resp = await client.post("/audio/transcriptions", data=data, files=files)
        except httpx.TimeoutException as exc:
            raise VoiceError(VOICE_UNAVAILABLE, "语音转写超时", status_code=504) from exc
        except httpx.HTTPError as exc:
            logger.warning("speech_stt_upstream_error", error_type=type(exc).__name__)
            raise VoiceError(VOICE_UNAVAILABLE, "语音转写服务不可用", status_code=502) from exc

        if resp.status_code == 401:
            raise VoiceError(VOICE_UNAVAILABLE, "语音服务凭据无效", status_code=502)
        if resp.status_code >= 400:
            logger.warning("speech_stt_http_error", status=resp.status_code)
            raise VoiceError(VOICE_UNAVAILABLE, "语音转写请求失败", status_code=502)

        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise VoiceError(VOICE_UNAVAILABLE, "语音转写响应无效", status_code=502) from exc

        text = str(payload.get("text") or "").strip()
        lang = payload.get("language")
        duration = payload.get("duration")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        return TranscriptionResult(
            text=text,
            language=str(lang) if lang else None,
            duration_seconds=float(duration) if duration is not None else None,
            provider=self.name,
            model=settings.speech_stt_model,
            usage=usage,
        )

    async def synthesize_stream(
        self,
        *,
        text: str,
        language: str | None = None,
        voice: str | None = None,
        output_format: str | None = None,
    ) -> AsyncIterator[bytes]:
        if not self.is_configured():
            raise VoiceError(VOICE_NOT_CONFIGURED, "语音服务未配置", status_code=503)
        fmt = (output_format or settings.speech_tts_format or "mp3").lower()
        body = {
            "model": settings.speech_tts_model,
            "input": text,
            "voice": voice or settings.speech_tts_voice,
            "response_format": fmt,
        }
        if language:
            body["language"] = language
        try:
            client = self._client_instance()
            async with client.stream("POST", "/audio/speech", json=body) as resp:
                if resp.status_code == 401:
                    raise VoiceError(VOICE_UNAVAILABLE, "语音服务凭据无效", status_code=502)
                if resp.status_code >= 400:
                    logger.warning("speech_tts_http_error", status=resp.status_code)
                    raise VoiceError(VOICE_UNAVAILABLE, "语音合成请求失败", status_code=502)
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk
        except VoiceError:
            raise
        except httpx.TimeoutException as exc:
            raise VoiceError(VOICE_UNAVAILABLE, "语音合成超时", status_code=504) from exc
        except httpx.HTTPError as exc:
            logger.warning("speech_tts_upstream_error", error_type=type(exc).__name__)
            raise VoiceError(VOICE_UNAVAILABLE, "语音合成服务不可用", status_code=502) from exc

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
