"""Grounded action documents for KaLM's pointwise retrieval model."""

from .questions import NEXT_ACTION


def control_values(actions, changed=None):
    """Describe observed values, optionally projecting one native local control change.

    These are browser control effects, not predictions about navigation or server state.
    Identity is the observed DOM node, never a label inferred from the user's goal.
    """
    rows, seen = [], set()
    for action in actions:
        node = action.get("node")
        if node is None or node in seen:
            continue
        seen.add(node)
        role = action.get("role")
        label = action["label"].split(" → ")[0]
        same = changed is not None and changed.get("node") == node
        if role in {"checkbox", "switch", "radio"} and action.get("checked") in {"true", "false"}:
            checked = action["checked"] == "true"
            if same and changed["kind"] == "click" and action.get("native_control") == "checkbox":
                checked = not checked
            if changed and changed.get("native_control") == "radio" and changed["kind"] == "click":
                if same:
                    checked = True
                elif action.get("radio_group") and action["radio_group"] == changed.get("radio_group"):
                    checked = False
            rows.append(label + ": " + ("enabled" if checked else "disabled"))
        elif action["kind"] == "select":
            value = action.get("current_value", "")
            if same and changed["kind"] == "select":
                value = changed["label"].split(" → ", 1)[-1]
            rows.append(label + ": " + value)
        elif action["kind"] == "fill":
            value = action.get("value", "")
            if same and changed["kind"] == "fill":
                value = "[text helper supplies the requested value]"
            rows.append(label + ": " + value)
    return "\n".join(rows)


def request(page, goal, model, targets, controls):
    """One finite choice over supported operation/target pairs plus terminal choices."""
    criteria = {}
    values = control_values(page["actions"])
    for operation, candidates in targets.items():
        for index, action in candidates.items():
            if action.get("native_control") == "checkbox" and action.get("checked") in {"true", "false"}:
                description = ("Disable " if action["checked"] == "true" else "Enable ") + action["label"]
            elif operation == "SELECT":
                description = "Set " + action["label"].replace(" → ", " to ", 1)
            elif operation == "TYPE_TEXT":
                description = "Enter text in " + action["label"]
            else:
                description = "Open or activate " + action["label"]
            context = action.get("context", "")
            if values:
                context = "Resulting control values:\n" + control_values(page["actions"], action)
                # Keep a result/link's local evidence when it is not a native value change.
                if action["kind"] == "click" and action.get("role") not in {"checkbox", "switch", "radio"}:
                    context += "\n" + action.get("context", "")
            criteria[f"{operation}:{index}"] = description + "\n" + context
    criteria.update({key: action["label"] for key, action in controls.items()})
    criteria["DONE"] = "Finish and remain on the current page: " + page["title"] + ".\n" + values
    if not values:
        criteria["DONE"] += "\nCurrent page content (not a navigation target):\n" + page.get("content", "")
    criteria["BLOCKED"] = "Stop because no supported operation can make progress toward the requested goal."
    if len(criteria) > 255:
        raise ValueError("KaLM supports at most 255 candidates per question; no targets discarded or action executed.")
    instructions = (
        "Given a browser task, retrieve the candidate action whose outcome best satisfies the task. " + NEXT_ACTION
    )
    return {"model": model, "state": goal, "questions": {
        "action": {"type": "choice", "criteria": criteria, "instructions": instructions},
    }}
