"""In-process fake speech provider for tests (no external calls)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

from app.providers.speech.base import AvailabilityState, SpeechCapabilities, SpeechProvider, TranscriptionResult
from app.providers.speech.errors import VOICE_UNAVAILABLE, VoiceError


class FakeSpeechProvider(SpeechProvider):
    name = "fake"

    def __init__(
        self,
        *,
        configured: bool = True,
        stt_text: str = "fake transcript",
        tts_payload: bytes = b"FAKEAUDIO",
        fail_stt: bool = False,
        fail_tts: bool = False,
    ) -> None:
        self._configured = configured
        self._stt_text = stt_text
        self._tts_payload = tts_payload
        self._fail_stt = fail_stt
        self._fail_tts = fail_tts
        self.transcribe_calls: list[dict] = []
        self.synthesize_calls: list[dict] = []

    def is_configured(self) -> bool:
        return self._configured

    async def check_availability(self) -> tuple[AvailabilityState, AvailabilityState]:
        if not self._configured:
            return "unconfigured", "unconfigured"
        return "configured", "configured"

    def capabilities(self) -> SpeechCapabilities:
        stt: AvailabilityState = "configured" if self._configured else "unconfigured"
        tts: AvailabilityState = stt
        return SpeechCapabilities(
            provider=self.name,
            stt_status=stt,
            tts_status=tts,
            stt_model="fake-stt",
            tts_model="fake-tts",
            tts_voice="fake-voice",
            tts_formats=["mp3", "wav"],
            input_formats=["webm", "ogg", "wav", "mp3", "m4a"],
            max_upload_bytes=25 * 1024 * 1024,
            max_duration_seconds=600,
            max_text_chars=4096,
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
        self.transcribe_calls.append(
            {
                "audio_path": audio_path,
                "filename": filename,
                "mime_type": mime_type,
                "language": language,
                "size": Path(audio_path).stat().st_size if Path(audio_path).exists() else 0,
            },
        )
        if self._fail_stt:
            raise VoiceError(VOICE_UNAVAILABLE, "fake stt failure", status_code=502)
        await asyncio.sleep(0)
        return TranscriptionResult(
            text=self._stt_text,
            language=language or "zh",
            duration_seconds=1.0,
            provider=self.name,
            model="fake-stt",
            usage={"seconds": 1.0},
        )

    async def synthesize_stream(
        self,
        *,
        text: str,
        language: str | None = None,
        voice: str | None = None,
        output_format: str | None = None,
    ) -> AsyncIterator[bytes]:
        self.synthesize_calls.append(
            {
                "text_len": len(text),
                "language": language,
                "voice": voice,
                "output_format": output_format,
            },
        )
        if self._fail_tts:
            raise VoiceError(VOICE_UNAVAILABLE, "fake tts failure", status_code=502)
        yield self._tts_payload
