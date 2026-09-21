"""Exercise backend contracts through HTTPX without network calls or model weights."""

import json
import os
from types import SimpleNamespace

import httpx
import pytest

from jev_ultrafast import model


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in list(os.environ):
        if name.startswith(("DECISION_", "TYPESAFE_", "TEXT_MODEL")):
            monkeypatch.delenv(name)


@pytest.fixture(autouse=True)
def http(monkeypatch):
    def unexpected(_request):
        pytest.fail("Unexpected model HTTP request")

    stub = SimpleNamespace(requests=[], respond=unexpected)

    def handle(request):
        stub.requests.append(request)
        return stub.respond(request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(model, "CLIENT", client)
        yield stub


@pytest.fixture
def page():
    return {
        "url": "https://example.test/search",
        "title": "Find a room",
        "text": "Choose a city and cancellation policy.",
        "actions": [
            {"id": "city-fill", "kind": "fill", "node": 10, "role": "textbox", "label": "City", "value": ""},
            {"id": "city-open", "kind": "click", "node": 10, "role": "textbox", "label": "City", "value": ""},
            {"id": "search", "kind": "click", "node": 20, "role": "button", "label": "Search"},
            {
                "id": "policy-any", "kind": "select", "node": 30, "role": "combobox",
                "label": "Policy → Any", "current_value": "Any", "value": "any",
            },
            {
                "id": "policy-free", "kind": "select", "node": 30, "role": "combobox",
                "label": "Policy → Free cancellation", "current_value": "Any", "value": "free",
            },
            {"id": "wait", "kind": "wait", "label": "Wait for loading"},
        ],
    }


def answer(ids, selected):
    return {"choice": selected, "confidence": 1.0, "probabilities": {key: float(key == selected) for key in ids}}


def result_for(request, operation="SELECT", target="3:2"):
    body = json.loads(request.content)
    questions = body["questions"]
    answers = {"operation": answer(questions["operation"]["criteria"], operation)}
    if operation in {"CLICK", "TYPE_TEXT", "SELECT"}:
        head = operation.lower() + "_target"
        answers[head] = answer(questions[head]["criteria"], target)
    return {"model": body["model"], "answers": answers, "usage": {"input_tokens": 25}}


def test_default_kalm_sends_all_heads_once_and_maps_observed_dropdown(http, page):
    http.respond = lambda request: httpx.Response(200, json=result_for(request))
    decision = model.choose(page, "Find a room with free cancellation", [])
    assert len(http.requests) == 1
    request = http.requests[0]
    assert str(request.url) == "http://127.0.0.1:8767/v1/systemone"
    assert request.method == "POST"
    assert "authorization" not in request.headers
    assert request.extensions["timeout"]["read"] == 120
    body = json.loads(request.content)
    assert body["model"] == "kalm-jev-nano"
    assert set(body["questions"]) == {"operation", "click_target", "type_text_target", "select_target"}
    assert set(body["questions"]["operation"]["criteria"]) == {
        "CLICK", "TYPE_TEXT", "SELECT", "WAIT", "DONE", "BLOCKED"
    }
    assert set(body["questions"]["click_target"]["criteria"]) == {"1", "2"}
    assert set(body["questions"]["type_text_target"]["criteria"]) == {"1"}
    assert set(body["questions"]["select_target"]["criteria"]) == {"3:1", "3:2"}
    assert body["questions"]["select_target"]["criteria"]["3:2"]["current_value"] == "Any"
    assert len(body["state"]["elements"]) == 3
    assert body["state"]["elements"][2]["options"][1]["value"] == "free"
    assert (decision["provider"], decision["operation"], decision["target"], decision["choice"]) == (
        "kalm", "SELECT", "3:2", "policy-free"
    )
    assert decision["probabilities"] == {"policy-any": 0.0, "policy-free": 1.0}


def test_explicit_typesafe_uses_legacy_credentials_and_model(http, page, monkeypatch):
    monkeypatch.setenv("DECISION_PROVIDER", "typesafe")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-typesafe-secret")
    monkeypatch.setenv("TYPESAFE_MODEL", "test-jev")
    http.respond = lambda request: httpx.Response(200, json=result_for(request, "CLICK", "2"))
    decision = model.choose(page, "Search", [])
    request = http.requests[0]
    assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
    assert request.headers["authorization"] == "Bearer test-typesafe-secret"
    assert request.extensions["timeout"]["read"] == 25
    assert json.loads(request.content)["model"] == "test-jev"
    assert decision["choice"] == "search"
    assert decision["provider"] == "typesafe"
    assert "test-typesafe-secret" not in json.dumps(decision)


@pytest.mark.parametrize("key", ["", "test-local-secret"])
def test_configured_service_timeout_and_optional_auth_reach_http(http, page, monkeypatch, key):
    monkeypatch.setenv("DECISION_BASE_URL", "http://localhost:9123/v1/")
    monkeypatch.setenv("DECISION_MODEL", "loaded-checkpoint")
    monkeypatch.setenv("DECISION_TIMEOUT", "7.5")
    monkeypatch.setenv("DECISION_API_KEY", key)
    http.respond = lambda request: httpx.Response(200, json=result_for(request, "WAIT"))
    decision = model.choose(page, "Wait for results", [])
    request = http.requests[0]
    assert str(request.url) == "http://localhost:9123/v1/systemone"
    assert all(value == 7.5 for value in request.extensions["timeout"].values())
    assert request.headers.get("authorization") == (f"Bearer {key}" if key else None)
    assert json.loads(request.content)["model"] == "loaded-checkpoint"
    assert decision["choice"] == "wait"
    assert decision["target"] is None


def test_invalid_unused_heads_cannot_override_selected_operation(http, page):
    def respond(request):
        result = result_for(request, "TYPE_TEXT", "1")
        result["answers"].update(click_target={"choice": "unobserved"}, select_target=["invalid"])
        return httpx.Response(200, json=result)

    http.respond = respond
    decision = model.choose(page, "Enter a city", [])
    assert decision["choice"] == "city-fill"
    assert decision["target_probabilities"] == {"1": 1.0}
    assert len(http.requests) == 1


@pytest.mark.parametrize(
    "malformed",
    ["invalid_json", "top_level_array", "answers_array", "missing_model", "missing_head", "unknown_target",
     "missing_probability", "probability_array", "nan_probability", "wrong_probability_sum",
     "boolean_confidence", "wrong_operation"],
)
def test_malformed_wire_response_never_becomes_a_decision(http, page, malformed):
    def respond(request):
        if malformed == "invalid_json":
            return httpx.Response(200, text="not json")
        if malformed == "top_level_array":
            return httpx.Response(200, json=[])
        result = result_for(request)
        selected = result["answers"]["select_target"]
        if malformed == "answers_array":
            result["answers"] = []
        elif malformed == "missing_model":
            del result["model"]
        elif malformed == "missing_head":
            del result["answers"]["select_target"]
        elif malformed == "unknown_target":
            selected.update(choice="3:999", probabilities={"3:1": 0.0, "3:999": 1.0})
        elif malformed == "missing_probability":
            del selected["probabilities"]["3:1"]
        elif malformed == "probability_array":
            selected["probabilities"] = [0.0, 1.0]
        elif malformed == "nan_probability":
            selected["probabilities"]["3:2"] = float("nan")
        elif malformed == "wrong_probability_sum":
            selected["probabilities"] = {"3:1": 0.6, "3:2": 0.6}
        elif malformed == "boolean_confidence":
            selected["confidence"] = True
        elif malformed == "wrong_operation":
            result["answers"]["operation"]["choice"] = "EXECUTE_SCRIPT"
        return httpx.Response(200, text=json.dumps(result), headers={"Content-Type": "application/json"})

    http.respond = respond
    with pytest.raises(ValueError, match="[Ii]nvalid.*[Rr]esponse|invalid JSON"):
        model.choose(page, "Find a room", [])
    assert len(http.requests) == 1


@pytest.mark.parametrize("kind", ["click", "select"])
def test_kalm_candidate_limit_rejects_without_truncation_or_network(http, page, kind):
    page["actions"] = [
        {
            "id": f"action-{index}", "kind": kind, "node": index if kind == "click" else 1,
            "label": f"Choice {index}", "value": str(index), "current_value": "0",
        }
        for index in range(256)
    ]
    with pytest.raises(ValueError, match="255 candidates.*no targets discarded"):
        model.choose(page, "Choose an option", [])
    assert http.requests == []
    assert len(page["actions"]) == 256


def test_422_is_actionable_and_does_not_leak_server_response(http, page):
    http.respond = lambda _request: httpx.Response(422, json={"detail": "private service debug payload"})
    with pytest.raises(RuntimeError, match="HTTP 422.*candidate and context limits") as raised:
        model.choose(page, "Find a room", [])
    assert "private service debug payload" not in str(raised.value)
    assert len(http.requests) == 1


@pytest.mark.parametrize("failure", ["connection", "unavailable"])
def test_local_failure_never_falls_back_to_paid_provider(http, page, monkeypatch, failure):
    monkeypatch.setenv("TYPESAFE_API_KEY", "must-not-be-used")
    monkeypatch.setattr(model.time, "sleep", lambda _duration: None)

    def respond(request):
        if failure == "connection":
            raise httpx.ConnectError("local service unavailable", request=request)
        return httpx.Response(503, json={"error": "local model loading"})

    http.respond = respond
    with pytest.raises(RuntimeError, match="[Nn]o action executed"):
        model.choose(page, "Find a room", [])
    assert len(http.requests) == (1 if failure == "connection" else 3)
    assert {str(request.url) for request in http.requests} == {"http://127.0.0.1:8767/v1/systemone"}
    assert all("authorization" not in request.headers for request in http.requests)


def test_explicit_typesafe_requires_key_before_any_request(http, page, monkeypatch):
    monkeypatch.setenv("DECISION_PROVIDER", "typesafe")
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY or DECISION_API_KEY"):
        model.choose(page, "Find a room", [])
    assert http.requests == []


def test_local_text_helper_accepts_no_key_and_omits_reasoning_fields(http, monkeypatch):
    monkeypatch.setenv("TEXT_MODEL_BASE_URL", "http://localhost:8000/v1/")
    monkeypatch.setenv("TEXT_MODEL", "local-writer")
    monkeypatch.setenv("TEXT_MODEL_REASONING", "omit")
    http.respond = lambda _request: httpx.Response(200, json={
        "choices": [{"message": {"content": '{"text":"Lisbon"}'}}]
    })
    context = {"goal": "Find a room in Lisbon", "field": {"label": "City"}}
    text, metadata = model.field_text(context)
    assert text == "Lisbon"
    assert metadata["model"] == "local-writer"
    assert len(http.requests) == 1
    request = http.requests[0]
    assert str(request.url) == "http://localhost:8000/v1/chat/completions"
    assert "authorization" not in request.headers
    body = json.loads(request.content)
    assert "reasoning" not in body and "thinking" not in body
    assert body["model"] == "local-writer"
    assert json.loads(body["messages"][1]["content"]) == context


def test_remote_text_helper_requires_key_before_request(http, monkeypatch):
    monkeypatch.setenv("TEXT_MODEL_BASE_URL", "https://writer.example.test/v1")
    with pytest.raises(ValueError, match="TEXT_MODEL_API_KEY for a remote helper"):
        model.field_text({"goal": "Enter Lisbon"})
    assert http.requests == []
