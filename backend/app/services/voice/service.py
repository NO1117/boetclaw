"""Voice orchestration service."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, AsyncIterator

from app.core.config import settings
from app.core.observability import new_trace_id
from app.providers.speech.errors import VOICE_NOT_CONFIGURED, VoiceError
from app.providers.speech.manager import speech_provider_manager
from app.services.voice.metrics import voice_metrics_tracker
from app.services.voice.rate_limiter import voice_rate_limiter
from app.services.voice.security import (
    tts_content_type,
    validate_audio_upload,
    validate_tts_format,
    validate_tts_text,
)
from app.services.voice.temp_store import voice_temp_store


class VoiceService:
    async def get_capabilities(self) -> dict[str, Any]:
        provider = speech_provider_manager.active()
        caps = provider.capabilities()
        if provider.is_configured():
            try:
                stt_status, tts_status = await provider.check_availability()
                caps.stt_status = stt_status
                caps.tts_status = tts_status
            except Exception:
                caps.stt_status = caps.tts_status = "unknown"
        return caps.to_dict()

    async def transcribe_upload(
        self,
        *,
        filename: str,
        declared_mime: str,
        data: bytes,
        language: str | None,
        rate_key: str,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        provider = speech_provider_manager.active()
        if not provider.is_configured():
            raise VoiceError(VOICE_NOT_CONFIGURED, "语音转写未配置", status_code=503)

        voice_rate_limiter.check(rate_key)
        safe_name, resolved_mime, _, duration_hint = validate_audio_upload(
            filename=filename,
            declared_mime=declared_mime,
            size=len(data),
            data=data,
        )
        await voice_rate_limiter.acquire()
        tid = trace_id or new_trace_id()
        voice_metrics_tracker.start(operation="stt", trace_id=tid)
        upload_started = time.monotonic()
        temp_path: Path | None = None
        try:
            temp_path, _ = voice_temp_store.allocate(Path(safe_name).suffix or ".bin")
            voice_temp_store.write(temp_path, data)
            upload_ms = round((time.monotonic() - upload_started) * 1000, 1)

            transcribe_started = time.monotonic()
            result = await provider.transcribe(
                audio_path=str(temp_path),
                filename=safe_name,
                mime_type=resolved_mime,
                language=language,
            )
            transcribe_ms = round((time.monotonic() - transcribe_started) * 1000, 1)

            estimated_cost = None
            if result.usage and isinstance(result.usage, dict):
                seconds = result.usage.get("seconds")
                if seconds is not None and settings.speech_stt_price_per_minute:
                    estimated_cost = round((float(seconds) / 60) * settings.speech_stt_price_per_minute, 6)

            voice_metrics_tracker.complete(
                tid,
                status="completed",
                provider=result.provider or provider.name,
                model=result.model,
                upload_ms=upload_ms,
                first_byte_ms=transcribe_ms,
                audio_bytes=len(data),
                audio_duration_seconds=result.duration_seconds or duration_hint,
                fmt=Path(safe_name).suffix.lstrip("."),
                estimated_cost=estimated_cost,
            )
            return {
                "text": result.text,
                "language": result.language,
                "duration_seconds": result.duration_seconds if result.duration_seconds is not None else duration_hint,
                "provider": result.provider or provider.name,
                "model": result.model,
                "trace_id": tid,
                "duration_ms": transcribe_ms,
            }
        except VoiceError as exc:
            voice_metrics_tracker.complete(
                tid,
                status="failed",
                provider=provider.name,
                failure_category=exc.code,
                audio_bytes=len(data) if data else None,
            )
            raise
        except Exception as exc:
            voice_metrics_tracker.complete(
                tid,
                status="failed",
                provider=provider.name,
                failure_category="internal_error",
                audio_bytes=len(data) if data else None,
            )
            raise VoiceError("VOICE_UNAVAILABLE", "语音转写失败", status_code=502) from exc
        finally:
            if temp_path is not None:
                voice_temp_store.remove(temp_path)
            voice_rate_limiter.release()

    async def synthesize_stream(
        self,
        *,
        text: str,
        language: str | None,
        voice: str | None,
        output_format: str | None,
        rate_key: str,
        trace_id: str | None = None,
    ) -> tuple[str, str, AsyncIterator[bytes], dict[str, Any]]:
        provider = speech_provider_manager.active()
        if not provider.is_configured():
            raise VoiceError(VOICE_NOT_CONFIGURED, "语音合成未配置", status_code=503)

        voice_rate_limiter.check(rate_key)
        cleaned = validate_tts_text(text)
        fmt = validate_tts_format(output_format)
        content_type = tts_content_type(fmt)
        await voice_rate_limiter.acquire()
        tid = trace_id or new_trace_id()
        voice_metrics_tracker.start(operation="tts", trace_id=tid)

        async def stream() -> AsyncIterator[bytes]:
            output_bytes = 0
            first_byte_ms: float | None = None
            started = time.monotonic()
            try:
                async for chunk in provider.synthesize_stream(
                    text=cleaned,
                    language=language,
                    voice=voice,
                    output_format=fmt,
                ):
                    if first_byte_ms is None:
                        first_byte_ms = round((time.monotonic() - started) * 1000, 1)
                    output_bytes += len(chunk)
                    yield chunk
                voice_metrics_tracker.complete(
                    tid,
                    status="completed",
                    provider=provider.name,
                    model=getattr(provider.capabilities(), "tts_model", None),
                    first_byte_ms=first_byte_ms,
                    input_chars=len(cleaned),
                    output_bytes=output_bytes,
                    fmt=fmt,
                )
            except VoiceError as exc:
                voice_metrics_tracker.complete(
                    tid,
                    status="failed",
                    provider=provider.name,
                    failure_category=exc.code,
                    input_chars=len(cleaned),
                )
                raise
            except Exception as exc:
                voice_metrics_tracker.complete(
                    tid,
                    status="failed",
                    provider=provider.name,
                    failure_category="internal_error",
                    input_chars=len(cleaned),
                )
                raise VoiceError("VOICE_UNAVAILABLE", "语音合成失败", status_code=502) from exc
            finally:
                voice_rate_limiter.release()

        meta = {
            "trace_id": tid,
            "provider": provider.name,
            "format": fmt,
            "input_chars": len(cleaned),
        }
        return content_type, fmt, stream(), meta


voice_service = VoiceService()
