"""Voice STT/TTS API routes."""

from __future__ import annotations

from hashlib import sha256

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.providers.speech.errors import VoiceError
from app.services.voice.service import voice_service

router = APIRouter(prefix="/voice", tags=["Voice"])

_READ_CHUNK_SIZE = 64 * 1024


class SpeechRequest(BaseModel):
    text: str = Field(..., min_length=1)
    language: str | None = None
    voice: str | None = None
    format: str | None = None


async def _read_upload_bounded(file: UploadFile, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await file.read(_READ_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise VoiceError("VOICE_FILE_TOO_LARGE", "音频文件超过大小限制", status_code=413)
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        await file.close()


def _rate_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() or request.headers.get("x-api-token", "")
    if token:
        return f"token:{sha256(token.encode('utf-8')).hexdigest()[:16]}"
    client = request.client.host if request.client else "unknown"
    return f"ip:{client}"


def _voice_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, VoiceError):
        return HTTPException(status_code=exc.status_code, detail=exc.to_detail())
    return HTTPException(status_code=400, detail={"code": "VOICE_UNAVAILABLE", "message": str(exc)})


@router.get("/capabilities")
async def voice_capabilities():
    return await voice_service.get_capabilities()


@router.post("/transcriptions")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    language: str | None = Form(None),
):
    from app.core.config import settings

    try:
        data = await _read_upload_bounded(file, max_bytes=settings.speech_max_upload_bytes)
        result = await voice_service.transcribe_upload(
            filename=file.filename or "audio.webm",
            declared_mime=file.content_type or "application/octet-stream",
            data=data,
            language=language or None,
            rate_key=_rate_key(request),
        )
        return result
    except VoiceError as exc:
        raise _voice_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "VOICE_UNAVAILABLE", "message": "转写失败"}) from exc


@router.post("/speech")
async def synthesize_speech(request: Request, body: SpeechRequest):
    try:
        content_type, fmt, stream, meta = await voice_service.synthesize_stream(
            text=body.text,
            language=body.language,
            voice=body.voice,
            output_format=body.format,
            rate_key=_rate_key(request),
        )
        headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "X-Voice-Trace-Id": meta["trace_id"],
            "X-Voice-Provider": meta["provider"],
            "X-Voice-Format": fmt,
            "Content-Disposition": f'inline; filename="speech.{fmt}"',
        }
        return StreamingResponse(stream, media_type=content_type, headers=headers)
    except VoiceError as exc:
        raise _voice_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "VOICE_UNAVAILABLE", "message": "合成失败"}) from exc
