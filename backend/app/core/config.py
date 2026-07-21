"""Application configuration."""

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    openai_api_key: str = ""
    openai_base_url: str = ""
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    google_api_key: str = ""

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "boetclaw"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    api_token: str = ""
    api_rate_limit_per_minute: int = 0
    console_password: str = ""
    console_jwt_secret: str = ""
    console_jwt_ttl_minutes: int = 480

    # Paths
    workspace_dir: Path = Field(default=BASE_DIR / "workspace")
    skills_dir: Path = Field(default=BASE_DIR / "skills")
    agents_md: Path = Field(default=BASE_DIR / "AGENTS.md")
    las_upload_max_bytes: int = 10 * 1024 * 1024

    # LangGraph checkpoints
    checkpoint_backend: str = "sqlite"  # sqlite|memory
    checkpoint_sqlite_path: Path = Field(default=BASE_DIR / "workspace" / "checkpoints")

    # Security (ToolGuard)
    tool_guard_enabled: bool = True
    tool_guard_level: str = "smart"  # strict|smart|auto|off
    tool_guard_denied_tools: str = ""
    file_guard_deny_dirs: str = ".env,.git,.ssh,.qwenpaw.secret"

    # Multi-agent
    default_agent_id: str = "default"
    agents_root: Path = Field(default=BASE_DIR / "workspace" / "agents")
    agent_idle_ttl_minutes: int = 30

    # Scheduler / Heartbeat
    heartbeat_enabled: bool = False
    heartbeat_interval_minutes: int = 120
    heartbeat_prompt: str = "汇总我的待办"

    # Provider (local model)
    ollama_base_url: str = "http://localhost:11434"
    provider_rate_limit_per_minute: int = 0

    # Plugins (comma-separated names; safe default: nothing enabled)
    enabled_plugins: str = ""
    plugins_dir: Path = Field(default=BASE_DIR / "plugins_ext")

    # Memory & context
    memory_backend: str = "file"  # file|store|none
    context_summarization_enabled: bool = False
    context_keep_messages: int = 20
    context_trigger_tokens: int = 4000

    # Speech / Voice (STT/TTS, decoupled from chat models)
    speech_provider: str = "openai_compatible"
    speech_api_key: str = ""
    speech_base_url: str = ""
    speech_stt_model: str = "whisper-1"
    speech_tts_model: str = "tts-1"
    speech_tts_voice: str = "alloy"
    speech_tts_format: str = "mp3"
    speech_max_upload_bytes: int = 25 * 1024 * 1024
    speech_max_duration_seconds: int = 600
    speech_max_text_chars: int = 4096
    speech_rate_limit_per_minute: int = 30
    speech_max_concurrent: int = 4
    speech_timeout_seconds: int = 120
    speech_temp_ttl_seconds: int = 300
    speech_stt_price_per_minute: float = 0.0
    speech_tts_price_per_million_chars: float = 0.0

    # Attachments
    attachment_ttl_days: int = 30
    attachment_chunk_max_chars: int = 4000
    attachment_max_chunks: int = 500
    attachment_max_parse_chars: int = 2_000_000
    attachment_retrieval_max_chunks: int = 8
    attachment_retrieval_max_chars: int = 24_000

    # Graph cache (isolated per-request agent graphs)
    graph_cache_max_size: int = 32
    graph_cache_ttl_seconds: int = 900

    # i18n
    lang: str = "zh"

    # Observability
    otel_enabled: bool = True
    otel_console_exporter: bool = False
    trace_persist_enabled: bool = True
    trace_persist_max_lines: int = 50000

    # MCP
    mcp_servers: str = "{}"

    # Gateway
    dingtalk_app_key: str = ""
    dingtalk_app_secret: str = ""
    dingtalk_webhook_secret: str = ""
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    qq_webhook_secret: str = ""
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    gateway_rate_limit_per_minute: int = 0

    @property
    def model_string(self) -> str:
        return f"{self.llm_provider}:{self.llm_model}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def denied_tools_list(self) -> list[str]:
        return [t.strip() for t in self.tool_guard_denied_tools.split(",") if t.strip()]

    @property
    def file_deny_dirs_list(self) -> list[str]:
        return [d.strip() for d in self.file_guard_deny_dirs.split(",") if d.strip()]

    @property
    def enabled_plugins_list(self) -> list[str]:
        return [p.strip() for p in self.enabled_plugins.split(",") if p.strip()]

    def get_mcp_servers_config(self) -> dict[str, Any]:
        import json

        try:
            return json.loads(self.mcp_servers)
        except json.JSONDecodeError:
            return {}


settings = Settings()
