"""Voice upload validation: format, MIME, signature, size, and duration."""

from __future__ import annotations

import io
import re
import struct
import wave
from pathlib import PurePosixPath

from app.core.config import settings
from app.providers.speech.errors import (
    VOICE_DURATION_EXCEEDED,
    VOICE_FILE_TOO_LARGE,
    VOICE_TEXT_TOO_LONG,
    VOICE_UNSUPPORTED_FORMAT,
    VoiceError,
)

ALLOWED_EXTENSIONS = {".webm", ".ogg", ".opus", ".wav", ".mp3", ".m4a"}
EXTENSION_TO_MIME = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}

_SAFE_FILENAME = re.compile(r'^[^/\\<>:"|?*\x00-\x1f]+$')


def normalize_filename(filename: str) -> str:
    name = (filename or "").strip().replace("\\", "/").split("/")[-1]
    if not name or ".." in name or not _SAFE_FILENAME.match(name):
        raise VoiceError(VOICE_UNSUPPORTED_FORMAT, "音频文件名无效")
    if len(name) > 512:
        raise VoiceError(VOICE_UNSUPPORTED_FORMAT, "音频文件名过长")
    return name


def extension_of(filename: str) -> str:
    lower = filename.lower()
    dot = lower.rfind(".")
    return lower[dot:] if dot >= 0 else ""


def detect_audio_signature(data: bytes, ext: str) -> str | None:
    if len(data) < 12:
        return None
    if data.startswith(b"\x1a\x45\xdf\xa3") and ext in {".webm"}:
        return "audio/webm"
    if data.startswith(b"OggS") and ext in {".ogg", ".opus"}:
        return "audio/ogg"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE" and ext == ".wav":
        return "audio/wav"
    if data.startswith(b"ID3") or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        if ext == ".mp3":
            return "audio/mpeg"
    if data[4:8] == b"ftyp" and ext == ".m4a":
        return "audio/mp4"
    return None


def estimate_duration_seconds(data: bytes, ext: str) -> float | None:
    if ext == ".wav":
        try:
            with wave.open(io.BytesIO(data), "rb") as handle:
                frames = handle.getnframes()
                rate = handle.getframerate() or 1
                return frames / float(rate)
        except wave.Error:
            return None
    if ext == ".mp3" and len(data) >= 4:
        # Conservative upper bound from file size and minimum plausible bitrate.
        min_bitrate = 32_000
        return (len(data) * 8) / min_bitrate
    if ext in {".webm", ".ogg", ".opus", ".m4a"}:
        min_bitrate = 16_000
        return (len(data) * 8) / min_bitrate
    return None


def validate_audio_upload(
    *,
    filename: str,
    declared_mime: str,
    size: int,
    data: bytes,
) -> tuple[str, str, str, float | None]:
    max_bytes = settings.speech_max_upload_bytes
    if size > max_bytes or len(data) > max_bytes:
        raise VoiceError(VOICE_FILE_TOO_LARGE, "音频文件超过大小限制", status_code=413)
    if size and abs(len(data) - size) > max(64, int(size * 0.05)):
        raise VoiceError(VOICE_UNSUPPORTED_FORMAT, "音频大小与声明不一致")

    safe_name = normalize_filename(filename)
    ext = extension_of(safe_name)
    if ext not in ALLOWED_EXTENSIONS:
        raise VoiceError(VOICE_UNSUPPORTED_FORMAT, f"不支持的音频格式: {ext or 'unknown'}")

    signature_mime = detect_audio_signature(data[:16], ext)
    if signature_mime is None:
        raise VoiceError(VOICE_UNSUPPORTED_FORMAT, "音频文件签名无效")

    declared = (declared_mime or "application/octet-stream").lower().split(";")[0].strip()
    expected = EXTENSION_TO_MIME.get(ext, signature_mime)
    if declared not in ("application/octet-stream", "", expected) and not declared.startswith("audio/"):
        raise VoiceError(VOICE_UNSUPPORTED_FORMAT, "声明 MIME 无效")
    if declared.startswith("audio/") and declared not in (expected, signature_mime):
        if declared.split("/")[0] != signature_mime.split("/")[0]:
            raise VoiceError(VOICE_UNSUPPORTED_FORMAT, "声明 MIME 与文件签名不一致")

    duration = estimate_duration_seconds(data, ext)
    max_duration = settings.speech_max_duration_seconds
    if duration is not None and duration > max_duration:
        raise VoiceError(VOICE_DURATION_EXCEEDED, "音频时长超过限制", status_code=413)

    # Reject path injection via filename.
    _ = PurePosixPath(safe_name).name
    return safe_name, expected, signature_mime, duration


def validate_tts_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        raise VoiceError(VOICE_UNSUPPORTED_FORMAT, "合成文本不能为空")
    if len(cleaned) > settings.speech_max_text_chars:
        raise VoiceError(VOICE_TEXT_TOO_LONG, "合成文本超过长度限制", status_code=413)
    return cleaned


def validate_tts_format(output_format: str | None) -> str:
    fmt = (output_format or settings.speech_tts_format or "mp3").lower().strip()
    allowed = {"mp3", "opus", "aac", "flac", "wav", "pcm"}
    if fmt not in allowed:
        raise VoiceError(VOICE_UNSUPPORTED_FORMAT, f"不支持的输出格式: {fmt}")
    return fmt


def tts_content_type(fmt: str) -> str:
    return {
        "mp3": "audio/mpeg",
        "opus": "audio/ogg",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "wav": "audio/wav",
        "pcm": "audio/pcm",
    }.get(fmt, "application/octet-stream")
