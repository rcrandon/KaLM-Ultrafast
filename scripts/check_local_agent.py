"""Run a bounded local reading task and verify the rendered result independently."""

import argparse
import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from jev_ultrafast import Agent
from jev_ultrafast.model import decision_settings

ARTICLES = {
    "choices": (
        "Open the article about using finite choices to control browser agents.",
        "A browser is a choice, not a conversation",
        "Freshness is part of correctness",
    ),
    "latency": (
        "Open the article about measuring network latency, model decisions, and page settling separately.",
        "Where the milliseconds go",
        "Measure the complete loop against an observable result",
    ),
    "uncertainty": (
        "Open the article about what confidence can and cannot tell you about an outcome.",
        "Confidence is not correctness",
        "Measure the complete loop against an observable result",
    ),
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/local-agent.json"))
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--article", choices=ARTICLES, default="choices")
    args = parser.parse_args()
    settings = decision_settings()
    if settings.provider != "kalm" or urlsplit(settings.base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("This check requires KaLM through a loopback endpoint; it never calls a paid decision API.")
    if not 1 <= args.steps <= 10:
        parser.error("Use 1 to 10 steps")
    directory = Path(__file__).resolve().parents[1] / "jev_ultrafast" / "static"
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    goal, expected_heading, expected_text = ARTICLES[args.article]
    report = {
        "goal": goal, "provider": settings.provider, "model": settings.model, "passed": False,
        "completion": "model_decision", "verification": "post_run_live_dom",
    }
    started = time.perf_counter()
    agent = None
    try:
        with Agent(
            f"http://127.0.0.1:{server.server_port}/fixture.html?scenario=research", goal,
        ) as agent:
            for _ in range(args.steps):
                state = agent.command("tick")
                print(json.dumps({"status": state["status"], "elapsed_ms": state["elapsed_ms"]}), flush=True)
                if state["status"] in {"done", "blocked"}:
                    break
            # Read the live DOM, not the model's DONE choice or its cached page.
            outcome = agent.browser.evaluate("""({
                heading: document.querySelector('main h1')?.textContent,
                article: !!document.querySelector('.article-content'),
                text: document.querySelector('.article-content')?.textContent,
                hash: location.hash
            })""")
            passed = (
                agent.state["status"] == "done"
                and outcome.get("article") is True
                and outcome.get("hash") == "#" + args.article
                and outcome.get("heading") == expected_heading
                and expected_text in (outcome.get("text") or "")
            )
            report.update(
                passed=passed, outcome=outcome, status=agent.state["status"],
                decisions=agent.state["decisions"], history=agent.state["history"],
            )
    except (ValueError, RuntimeError, TimeoutError) as error:
        report["error"] = str(error)
    finally:
        if agent is not None:
            report.update(
                status=agent.state["status"], decisions=agent.state["decisions"], history=agent.state["history"],
            )
        server.shutdown()
        server.server_close()
        report["wall_ms"] = round((time.perf_counter() - started) * 1000)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"decisions", "history"}}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
