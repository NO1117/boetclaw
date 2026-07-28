"""Speech provider registry."""

from __future__ import annotations

from app.providers.speech.base import SpeechProvider
from app.providers.speech.fake import FakeSpeechProvider
from app.providers.speech.openai_compatible import OpenAICompatibleSpeechProvider


class SpeechProviderManager:
    def __init__(self) -> None:
        self._providers: dict[str, SpeechProvider] = {}
        self.register(OpenAICompatibleSpeechProvider())
        self.register(FakeSpeechProvider(configured=False))

    def register(self, provider: SpeechProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str | None = None) -> SpeechProvider:
        from app.core.config import settings

        key = (name or settings.speech_provider or "openai_compatible").strip()
        if key not in self._providers:
            raise ValueError(f"未知 speech provider: {key}")
        return self._providers[key]

    def active(self) -> SpeechProvider:
        return self.get()


speech_provider_manager = SpeechProviderManager()
