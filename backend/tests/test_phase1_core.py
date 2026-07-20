"""Phase 1 tests: middleware, agent factory, startup."""


def test_observability_middleware_importable():
    from app.middleware.observability_mw import ObservabilityMiddleware

    mw = ObservabilityMiddleware()
    assert mw.name == "boetclaw_observability"
    # hooks exist
    assert hasattr(mw, "before_model")
    assert hasattr(mw, "wrap_tool_call")


def test_factory_importable_and_subagents():
    from app.core.agent_factory import build_default_subagents

    subs = build_default_subagents()
    names = {s["name"] for s in subs}
    assert {"researcher", "coder", "chart-analyst", "reviewer"} <= names


def test_startup_functions_exist():
    from app.core.startup import phase1_fast, phase2_background

    assert callable(phase1_fast)
    assert callable(phase2_background)
