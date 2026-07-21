"""Stable voice error codes for API responses."""

from __future__ import annotations

VOICE_NOT_CONFIGURED = "VOICE_NOT_CONFIGURED"
VOICE_UNAVAILABLE = "VOICE_UNAVAILABLE"
VOICE_FILE_TOO_LARGE = "VOICE_FILE_TOO_LARGE"
VOICE_DURATION_EXCEEDED = "VOICE_DURATION_EXCEEDED"
VOICE_UNSUPPORTED_FORMAT = "VOICE_UNSUPPORTED_FORMAT"
VOICE_TEXT_TOO_LONG = "VOICE_TEXT_TOO_LONG"
VOICE_RATE_LIMITED = "VOICE_RATE_LIMITED"


class VoiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}
