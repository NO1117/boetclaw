"""Speech provider abstraction (STT/TTS), decoupled from chat models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

AvailabilityState = Literal["configured", "unconfigured", "unavailable", "unknown"]


@dataclass
class SpeechCapabilities:
    provider: str
    stt_status: AvailabilityState
    tts_status: AvailabilityState
    stt_model: str | None = None
    tts_model: str | None = None
    tts_voice: str | None = None
    tts_formats: list[str] = field(default_factory=list)
    input_formats: list[str] = field(default_factory=list)
    max_upload_bytes: int = 0
    max_duration_seconds: int = 0
    max_text_chars: int = 0
    browser_fallback: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "stt": {
                "status": self.stt_status,
                "model": self.stt_model,
                "formats": self.input_formats,
                "max_upload_bytes": self.max_upload_bytes,
                "max_duration_seconds": self.max_duration_seconds,
            },
            "tts": {
                "status": self.tts_status,
                "model": self.tts_model,
                "voice": self.tts_voice,
                "formats": self.tts_formats,
                "max_text_chars": self.max_text_chars,
            },
            "browser_fallback": self.browser_fallback,
        }


@dataclass
class TranscriptionResult:
    text: str
    language: str | None = None
    duration_seconds: float | None = None
    provider: str | None = None
    model: str | None = None
    usage: dict[str, Any] | None = None


class SpeechProvider(ABC):
    name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """Whether credentials and endpoints are present."""

    @abstractmethod
    async def check_availability(self) -> tuple[AvailabilityState, AvailabilityState]:
        """Return (stt_status, tts_status)."""

    @abstractmethod
    async def transcribe(
        self,
        *,
        audio_path: str,
        filename: str,
        mime_type: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio from a local temp file path."""

    @abstractmethod
    async def synthesize_stream(
        self,
        *,
        text: str,
        language: str | None = None,
        voice: str | None = None,
        output_format: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream synthesized audio bytes."""

    def capabilities(self) -> SpeechCapabilities:
        stt, tts = "unknown", "unknown"
        if not self.is_configured():
            stt = tts = "unconfigured"
        return SpeechCapabilities(
            provider=self.name,
            stt_status=stt,
            tts_status=tts,
        )
