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
    if "action" in questions:
        selected = f"{operation}:{target}" if operation in {"CLICK", "SELECT", "TYPE_TEXT"} else operation
        return {"model": body["model"], "answers": {"action": answer(questions["action"]["criteria"], selected)}}
    answers = {"operation": answer(questions["operation"]["criteria"], operation)}
    if operation in {"CLICK", "TYPE_TEXT", "SELECT"}:
        head = operation.lower() + "_target"
        answers[head] = answer(questions[head]["criteria"], target)
    return {"model": body["model"], "answers": answers, "usage": {"input_tokens": 25}}


def test_kalm_joint_choice_maps_observed_option_and_preserves_goal(http, page):
    http.respond = lambda request: httpx.Response(200, json=result_for(request))
    decision = model.choose(page, "Find a room with free cancellation", [])
    assert len(http.requests) == 1
    request = http.requests[0]
    assert str(request.url) == "http://127.0.0.1:8767/v1/systemone"
    assert "authorization" not in request.headers
    assert request.extensions["timeout"]["read"] == 120
    body = json.loads(request.content)
    assert body["state"] == "Find a room with free cancellation"
    assert set(body["questions"]) == {"action"}
    head = body["questions"]["action"]
    assert set(head["criteria"]) == {
        "CLICK:1", "CLICK:2", "TYPE_TEXT:1", "SELECT:3:1", "SELECT:3:2", "WAIT", "DONE", "BLOCKED"
    }
    assert "Policy: Free cancellation" in head["criteria"]["SELECT:3:2"]
    assert "Policy: Any" in head["criteria"]["DONE"]
    assert model.NEXT_ACTION in head["instructions"]
    assert (decision["provider"], decision["operation"], decision["target"], decision["choice"]) == (
        "kalm", "SELECT", "3:2", "policy-free"
    )
    assert decision["score_mode"] == "joint_action"
    assert decision["probabilities"] == {"policy-any": 0.0, "policy-free": 1.0}


def test_kalm_keeps_local_context_and_records_recent_actions(http, page):
    page["actions"][2]["context"] = "Search rooms with the selected cancellation policy."
    history = [{"action": "City", "kind": "fill", "text": "Oslo", "page_changed": True}]
    http.respond = lambda request: httpx.Response(200, json=result_for(request, "CLICK", "2"))
    decision = model.choose(page, "Find a room in Oslo", history)
    body = json.loads(http.requests[0].content)
    head = body["questions"]["action"]
    assert page["actions"][2]["context"] in head["criteria"]["CLICK:2"]
    assert decision["observation"]["recent_actions"] == history
    assert body["state"] == "Find a room in Oslo"


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
    assert json.loads(request.content)["questions"]["operation"]["criteria"]["DONE"] == (
        "Every requirement is visibly satisfied."
    )


def test_kalm_done_is_the_model_choice_in_the_same_request_not_a_local_page_rule(http, page):
    http.respond = lambda request: httpx.Response(200, json=result_for(request, "DONE"))
    decision = model.choose(page, "Search for a room", [])
    assert len(http.requests) == 1
    assert decision["operation"] == decision["choice"] == "DONE"
    assert decision["target"] is None
    assert decision["raw_answers"]["action"]["choice"] == "DONE"
    # Unused target heads need not exist when the operation is terminal.
    assert set(decision["raw_answers"]) == {"action"}


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


def test_invalid_unused_heads_cannot_override_selected_operation(http, page, monkeypatch):
    monkeypatch.setenv("DECISION_PROVIDER", "typesafe")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
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
@pytest.mark.parametrize("provider", ["kalm", "typesafe"])
def test_malformed_wire_response_never_becomes_a_decision(http, page, malformed, provider, monkeypatch):
    monkeypatch.setenv("DECISION_PROVIDER", provider)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    def respond(request):
        if malformed == "invalid_json":
            return httpx.Response(200, text="not json")
        if malformed == "top_level_array":
            return httpx.Response(200, json=[])
        result = result_for(request)
        head = "action" if provider == "kalm" else "select_target"
        selected = result["answers"][head]
        prefix = "SELECT:" if provider == "kalm" else ""
        if malformed == "answers_array":
            result["answers"] = []
        elif malformed == "missing_model":
            del result["model"]
        elif malformed == "missing_head":
            del result["answers"][head]
        elif malformed == "unknown_target":
            selected["choice"] = prefix + "3:999"
        elif malformed == "missing_probability":
            del selected["probabilities"][prefix + "3:1"]
        elif malformed == "probability_array":
            selected["probabilities"] = [0.0, 1.0]
        elif malformed == "nan_probability":
            selected["probabilities"][prefix + "3:2"] = float("nan")
        elif malformed == "wrong_probability_sum":
            selected["probabilities"] = {"3:1": 0.6, "3:2": 0.6}
        elif malformed == "boolean_confidence":
            selected["confidence"] = True
        elif malformed == "wrong_operation":
            result["answers"]["action" if provider == "kalm" else "operation"]["choice"] = "EXECUTE_SCRIPT"
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


def test_llama_cpp_text_request_disables_thinking_without_changing_server(http, monkeypatch):
    monkeypatch.setenv("TEXT_MODEL_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("TEXT_MODEL_REASONING", "llama_cpp")
    monkeypatch.setenv("TEXT_MODEL_TIMEOUT", "90")
    http.respond = lambda _request: httpx.Response(200, json={
        "choices": [{"message": {"content": '{"text":"Lisbon"}'}}],
    })
    assert model.field_text({"goal": "Find Lisbon"})[0] == "Lisbon"
    request = http.requests[0]
    body = json.loads(request.content)
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert "reasoning" not in body and "thinking" not in body
    assert request.extensions["timeout"]["read"] == 90
