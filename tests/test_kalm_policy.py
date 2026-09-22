"""Control effects and probability projections must preserve observed identity."""

import httpx

from jev_ultrafast import kalm_policy, model


def test_duplicate_labels_do_not_toggle_another_node_or_invert_a_radio():
    actions = [
        {"id": "a", "node": 1, "kind": "click", "role": "checkbox", "label": "Updates", "checked": "false"},
        {"id": "b", "node": 2, "kind": "click", "role": "checkbox", "label": "Updates", "checked": "false"},
        {"id": "c", "node": 3, "kind": "click", "role": "radio", "label": "Weekly", "checked": "true"},
    ]
    for action in actions:
        action["native_control"] = action["role"]
    assert kalm_policy.control_values(actions, actions[1]).splitlines() == [
        "Updates: disabled", "Updates: enabled", "Weekly: enabled",
    ]
    assert kalm_policy.control_values(actions, actions[2]) == kalm_policy.control_values(actions)


def test_native_radio_projection_clears_only_its_group_and_aria_toggle_is_unknown():
    actions = [
        {"node": 1, "kind": "click", "role": "radio", "native_control": "radio",
         "radio_group": "group-a", "label": "Daily", "checked": "true"},
        {"node": 2, "kind": "click", "role": "radio", "native_control": "radio",
         "radio_group": "group-a", "label": "Weekly", "checked": "false"},
        {"node": 3, "kind": "click", "role": "radio", "native_control": "radio",
         "radio_group": "group-b", "label": "Other", "checked": "true"},
        {"node": 4, "kind": "click", "role": "switch", "label": "Custom toggle", "checked": "false"},
    ]
    assert kalm_policy.control_values(actions, actions[1]).splitlines() == [
        "Daily: disabled", "Weekly: enabled", "Other: enabled", "Custom toggle: disabled",
    ]
    assert kalm_policy.control_values(actions, actions[3]) == kalm_policy.control_values(actions)


def test_joint_winner_is_not_replaced_by_a_larger_operation_marginal(monkeypatch):
    monkeypatch.setenv("DECISION_PROVIDER", "kalm")
    page = {"url": "https://example.test", "title": "Settings", "text": "", "actions": [
        {"id": "button", "node": 1, "kind": "click", "label": "Apply"},
        {"id": "one", "node": 2, "kind": "select", "label": "Theme → One", "value": "1"},
        {"id": "two", "node": 2, "kind": "select", "label": "Theme → Two", "value": "2"},
    ]}
    def respond(_request):
        return httpx.Response(200, json={"model": "test", "answers": {"action": {
            "choice": "CLICK:1", "confidence": 0.1,
            "probabilities": {"CLICK:1": 0.34, "SELECT:2:1": 0.33, "SELECT:2:2": 0.33, "DONE": 0, "BLOCKED": 0},
        }}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(model, "CLIENT", client)
        decision = model.choose(page, "Apply settings", [])
    assert decision["choice"] == "button"
    assert decision["operation_probabilities"]["SELECT"] == 0.66
    assert decision["target_probabilities"] == {"1": 1.0}
