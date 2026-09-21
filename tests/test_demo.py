"""Inspector metadata and local fixtures never require a live model or browser."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from jev_ultrafast import demo


@pytest.fixture
def settings(monkeypatch):
    configured = SimpleNamespace(
        provider="kalm",
        model="KaLM-Jev-test",
        base_url="https://private-service.test/v1?token=private-endpoint-token",
        api_key="private-api-key",
        timeout=120,
    )
    monkeypatch.setattr(demo.model, "decision_settings", lambda: configured)
    monkeypatch.setattr(demo, "AGENT", None)
    return configured


@pytest.mark.parametrize("provider", ["kalm", "typesafe"])
def test_state_exposes_model_identity_without_connection_secrets(settings, provider):
    settings.provider = provider
    state = demo.response_state()
    assert state["decision_provider"] == provider
    assert state["decision_model"] == settings.model
    assert state["status"] == "idle"
    encoded = json.dumps(state)
    assert settings.api_key not in encoded
    assert settings.base_url not in encoded
    assert "private-endpoint-token" not in encoded
    assert "api_key" not in state
    assert "base_url" not in state


def test_backend_metadata_preserves_active_agent_snapshot(settings, monkeypatch):
    snapshot = {"status": "ready", "page": {"title": "Reading room"}, "history": []}
    agent = Mock(snapshot=Mock(return_value=snapshot))
    monkeypatch.setattr(demo, "AGENT", agent)
    state = demo.response_state()
    assert state["page"] == snapshot["page"]
    assert state["status"] == "ready"
    assert "decision_provider" not in snapshot


def test_default_demo_uses_local_reading_room(settings, monkeypatch):
    agent = Mock(state={}, snapshot=Mock(return_value={"status": "ready"}))
    constructor = Mock(return_value=agent)
    monkeypatch.setattr(demo, "Agent", constructor)
    goal = "Open the article about using finite choices to control browser agents."
    demo.command("reset", {"goal": goal})
    assert constructor.call_args.args == (f"{demo.ORIGIN}/fixture.html?scenario=research", goal)
    assert agent.state["scenario"] == "research"


def test_environment_reads_utf8_bom_and_keeps_existing_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INSPECTOR_UTF8_TEST", raising=False)
    monkeypatch.setenv("INSPECTOR_EXISTING_TEST", "existing")
    (tmp_path / ".env").write_text(
        "INSPECTOR_UTF8_TEST=Zürich → London\nINSPECTOR_EXISTING_TEST=changed\n", encoding="utf-8-sig"
    )
    demo.load_environment()
    assert demo.os.environ["INSPECTOR_UTF8_TEST"] == "Zürich → London"
    assert demo.os.environ["INSPECTOR_EXISTING_TEST"] == "existing"


def test_static_page_preserves_utf8_and_injects_local_token(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("Zürich → London __TOKEN__", encoding="utf-8")
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    handler = demo.Handler.__new__(demo.Handler)
    handler.path = "/"
    handler.headers = {"Host": f"127.0.0.1:{demo.PORT}"}
    handler.send = Mock()
    handler.do_GET()
    handler.send.assert_called_once_with(200, f"Zürich → London {demo.TOKEN}", "text/html; charset=utf-8")
