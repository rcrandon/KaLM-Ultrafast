"""Evaluate model-selected checkbox/dropdown actions and completion on a local fixture."""

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

CASES = {
    "digest": ("Enable the weekly email digest.", True, "Light"),
    "theme": ("Change the color theme to Dark.", False, "Dark"),
    "both": ("Enable the weekly email digest and change the color theme to Dark.", True, "Dark"),
    "already": ("Keep the weekly email digest disabled and the color theme set to Light.", False, "Light"),
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, default="both")
    parser.add_argument("--output", type=Path, default=Path("artifacts/preferences.json"))
    parser.add_argument("--steps", type=int, default=4)
    args = parser.parse_args()
    settings = decision_settings()
    if settings.provider != "kalm" or urlsplit(settings.base_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("This check requires a loopback KaLM service.")
    if not 1 <= args.steps <= 10:
        parser.error("Use 1 to 10 steps")
    root = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    goal, digest, theme = CASES[args.case]
    report = {"case": args.case, "goal": goal, "passed": False, "completion": "model_decision"}
    started = time.perf_counter()
    agent = None
    try:
        with Agent(f"http://127.0.0.1:{server.server_port}/preferences.html", goal) as agent:
            for _ in range(args.steps):
                state = agent.command("tick")
                print(json.dumps({"status": state["status"], "elapsed_ms": state["elapsed_ms"]}), flush=True)
                if state["status"] in {"done", "blocked"}:
                    break
            outcome = agent.browser.evaluate("""({
                digest:document.getElementById('digest').checked,
                theme:document.getElementById('theme').value
            })""")
            report.update(outcome=outcome, passed=(
                agent.state["status"] == "done" and outcome == {"digest": digest, "theme": theme}
            ))
    except (ValueError, RuntimeError, TimeoutError) as error:
        report["error"] = str(error)
    finally:
        if agent is not None:
            report.update({k: agent.state[k] for k in ("status", "decisions", "history", "elapsed_ms")})
        server.shutdown()
        server.server_close()
        report["wall_ms"] = round((time.perf_counter() - started) * 1000)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"decisions", "history"}}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
