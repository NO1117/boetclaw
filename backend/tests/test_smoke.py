"""Phase 0 smoke tests."""


def test_import_app():
    from app.main import app

    assert app.title == "BoetClaw DeepAgents"


def test_config_new_fields():
    from app.core.config import settings

    assert settings.tool_guard_level in {"strict", "smart", "auto", "off"}
    assert settings.default_agent_id == "default"
    assert isinstance(settings.file_deny_dirs_list, list)


def test_event_types_extended():
    from app.core.observability import EventType

    assert EventType.PLAN_CREATED.value == "plan_created"
    assert EventType.GUARD_BLOCK.value == "guard_block"
