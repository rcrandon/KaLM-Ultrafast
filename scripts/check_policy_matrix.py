"""Evaluate labeled development states, including partial completion and recovery failures."""

import argparse
import hashlib
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from jev_ultrafast.browser import Browser
from jev_ultrafast.model import choose, decision_settings


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def capture(origin):
    cases = []
    browser = Browser(origin + "/tests/fixtures/preferences.html")
    try:
        goal = "Enable the weekly email digest and change the color theme to Dark."
        for name, digest, theme, expected in [
            ("prefs-none", False, "Light", ["CLICK:Weekly email digest", "SELECT:Color theme → Dark"]),
            ("prefs-theme", False, "Dark", ["CLICK:Weekly email digest"]),
            ("prefs-digest", True, "Light", ["SELECT:Color theme → Dark"]),
            ("prefs-complete", True, "Dark", ["DONE"]),
        ]:
            # Labeled fixture setup only. These values never enter the agent's planner or executor.
            browser.evaluate(
                f"document.getElementById('digest').checked={json.dumps(digest)};"
                f"document.getElementById('theme').value={json.dumps(theme)};report()"
            )
            cases.append({"id": name, "goal": goal, "page": browser.observe(screenshot=False), "expected": expected})
        for name, source, goal, expected in [
            ("digest-initial", 0, "Enable the weekly email digest.", ["CLICK:Weekly email digest"]),
            ("digest-satisfied", 2, "Enable the weekly email digest.", ["DONE"]),
            ("theme-initial", 0, "Change the color theme to Dark.", ["SELECT:Color theme → Dark"]),
            ("already-correct", 0, "Keep the weekly email digest disabled and the color theme set to Light.", ["DONE"]),
        ]:
            cases.append({"id": name, "goal": goal, "page": cases[source]["page"], "expected": expected})
    finally:
        browser.close()
    goals = [
        ("choices", "Open the article about using finite choices to control browser agents.",
         "A browser is a choice, not a conversation"),
        ("latency", "Open the article about measuring network latency, model decisions, and page settling separately.",
         "Where the milliseconds go"),
        ("uncertainty", "Open the article about what confidence can and cannot tell you about an outcome.",
         "Confidence is not correctness"),
    ]
    browser = Browser(origin + "/jev_ultrafast/static/fixture.html?scenario=research")
    try:
        listing = browser.observe(screenshot=False)
        for slug, goal, title in goals:
            cases.append({"id": "list-" + slug, "goal": goal, "page": listing, "expected": ["CLICK:" + title]})
            browser.evaluate("article(" + json.dumps(slug) + ");location.hash=" + json.dumps(slug))
            page = browser.observe(screenshot=False)
            cases.append({"id": "open-" + slug, "goal": goal, "page": page, "expected": ["DONE"]})
            if slug == "choices":
                for other, other_goal, _ in goals[1:]:
                    cases.append({"id": "wrong-" + other, "goal": other_goal, "page": page,
                                  "expected": ["CLICK:← Reading room", "CLICK:Reading room"]})
    finally:
        browser.close()
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/policy-matrix.json"))
    args = parser.parse_args()
    settings = decision_settings()
    if settings.provider != "kalm" or urlsplit(settings.base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Use the loopback KaLM service; this check does not call a paid provider.")
    root = Path(__file__).resolve().parents[1]
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    rows = []
    report = {
        "evaluation": "development fixtures, not a held-out browser benchmark",
        "source_sha256": {str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [root / "jev_ultrafast/model.py", root / "jev_ultrafast/kalm_policy.py",
                                    root / "jev_ultrafast/snapshot.js", root / "jev_ultrafast/static/fixture.html",
                                    root / "tests/fixtures/preferences.html"]},
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        cases = capture(f"http://127.0.0.1:{server.server_port}")
        for case in cases:
            decision = choose(case["page"], case["goal"], [])
            action = next((a for a in case["page"]["actions"] if a["id"] == decision["choice"]), None)
            actual = (decision["operation"] + ":" + action["label"]
                      if action and decision["target"] else decision["operation"])
            row = {**case, "actual": actual, "passed": actual in case["expected"], "decision": decision}
            rows.append(row)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            summary = {k: v for k, v in row.items() if k not in {"page", "decision"}}
            print(json.dumps(summary), flush=True)
    finally:
        server.shutdown()
        server.server_close()
    report.update(passed=sum(row["passed"] for row in rows), total=len(rows))
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{report['passed']}/{report['total']} development states passed")
    raise SystemExit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
