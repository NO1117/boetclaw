"""Retry classification and backoff calculation."""

from __future__ import annotations

import random
from typing import Any

from app.services.task_queue.models import BackoffStrategy, ErrorCategory


_NON_RETRYABLE_MARKERS = (
    "permission",
    "forbidden",
    "unauthorized",
    "validation",
    "invalid",
    "config",
    "security",
    "denied",
    "cancelled",
    "canceled",
)


def classify_error(exc: BaseException | str, *, cancelled: bool = False) -> ErrorCategory:
    if cancelled:
        return ErrorCategory.CANCELLED
    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        return ErrorCategory.TIMEOUT
    if any(marker in message for marker in _NON_RETRYABLE_MARKERS):
        if "permission" in message or "forbidden" in message or "unauthorized" in message:
            return ErrorCategory.PERMISSION
        if "validation" in message or "invalid" in message:
            return ErrorCategory.VALIDATION
        if "security" in message or "denied" in message:
            return ErrorCategory.SECURITY
        if "config" in message:
            return ErrorCategory.CONFIG
        return ErrorCategory.NON_RETRYABLE
    return ErrorCategory.RETRYABLE


def is_retryable(category: ErrorCategory) -> bool:
    return category in {ErrorCategory.RETRYABLE, ErrorCategory.TIMEOUT, ErrorCategory.UNKNOWN}


def compute_backoff_seconds(
    *,
    strategy: BackoffStrategy,
    attempt_number: int,
    base_seconds: int,
    max_seconds: int,
    jitter: bool = True,
) -> int:
    attempt = max(1, attempt_number)
    if strategy == BackoffStrategy.FIXED:
        delay = base_seconds
    elif strategy == BackoffStrategy.LINEAR:
        delay = base_seconds * attempt
    else:
        delay = base_seconds * (2 ** (attempt - 1))
    delay = min(max_seconds, max(1, delay))
    if jitter:
        jitter_range = max(1, int(delay * 0.2))
        delay = max(1, delay + random.randint(-jitter_range, jitter_range))
    return min(max_seconds, delay)


def build_retry_payload(
    *,
    category: ErrorCategory,
    attempt_number: int,
    delay_seconds: int,
    error: str,
) -> dict[str, Any]:
    return {
        "category": category.value,
        "attempt_number": attempt_number,
        "delay_seconds": delay_seconds,
        "error": error,
    }
