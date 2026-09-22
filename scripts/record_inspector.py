"""Record the real local inspector at original speed, with an independent outcome check."""

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from jev_ultrafast.browser import Browser
from jev_ultrafast.model import decision_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--output", type=Path, default=Path("artifacts/recording"))
    parser.add_argument("--media", type=Path, default=Path("docs/media"))
    args = parser.parse_args()
    if decision_settings().provider != "kalm":
        parser.error("Record this local demonstration with KaLM.")
    if args.port == 8766:
        parser.error("Use a separate inspector port, leaving the normal inspector available.")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        parser.error("Install ffmpeg before recording.")
    args.output.mkdir(parents=True, exist_ok=False)
    args.media.mkdir(parents=True, exist_ok=True)
    os.environ["TYPESAFE_DEMO_PORT"] = str(args.port)
    from jev_ultrafast import demo

    server = ThreadingHTTPServer(("127.0.0.1", args.port), demo.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    browser = None
    frames = []
    start = None
    report = {"passed": False, "playback_speed": 1, "frame_sampling_seconds": 0.5}
    try:
        browser = Browser(demo.ORIGIN)
        browser.call("Emulation.setDeviceMetricsOverride", width=1440, height=1180, deviceScaleFactor=1, mobile=False)
        browser.call("Runtime.evaluate", expression="document.fonts.ready", awaitPromise=True)
        browser.evaluate("document.getElementById('start').click()")
        deadline = time.monotonic() + 30
        while browser.evaluate("document.getElementById('choose').disabled"):
            if time.monotonic() > deadline:
                raise RuntimeError("Inspector did not open its fixture.")
            time.sleep(0.1)

        def frame():
            timestamp = time.perf_counter() - start
            name = f"frame-{len(frames):05d}.jpg"
            data = browser.call("Page.captureScreenshot", format="jpeg", quality=88, _response_timeout=30)["data"]
            (args.output / name).write_bytes(base64.b64decode(data))
            frames.append((timestamp, name))

        def wait_ready():
            deadline = time.monotonic() + 180
            while True:
                frame()
                error = browser.evaluate("document.getElementById('error').hidden ? '' : "
                                         "document.getElementById('error').textContent")
                if error:
                    raise RuntimeError(error)
                if not browser.evaluate("document.getElementById('start').disabled"):
                    return
                if time.monotonic() > deadline:
                    raise RuntimeError("Recording exceeded the per-decision time limit.")
                time.sleep(0.5)

        browser.call("Page.bringToFront")
        start = time.perf_counter()
        frame()
        for step in range(4):
            browser.evaluate("document.getElementById('choose').click()")
            wait_ready()
            if step == 0:
                (args.output / "inspector.png").write_bytes(base64.b64decode(
                    browser.call("Page.captureScreenshot", format="png", _response_timeout=30)["data"]
                ))
            browser.evaluate("document.getElementById('execute').click()")
            wait_ready()
            if demo.AGENT.state["status"] in {"done", "blocked"}:
                break
        elapsed = time.perf_counter() - start
        outcome = demo.AGENT.browser.evaluate("""({
            heading: document.querySelector('main h1')?.textContent,
            article: !!document.querySelector('.article-content'),
            hash: location.hash
        })""")
        state = demo.AGENT.snapshot()
        passed = (state["status"] == "done" and outcome == {
            "heading": "A browser is a choice, not a conversation", "article": True, "hash": "#choices",
        })
        root = Path(__file__).resolve().parents[1]
        report.update(
            passed=passed, goal=state["goal"], outcome=outcome, status=state["status"],
            interaction_seconds=round(elapsed, 3), agent_elapsed_ms=state["elapsed_ms"],
            operations=[d["operation"] for d in state["decisions"]],
            decision_calls=len(state["decisions"]), text_calls=len(state["text_calls"]),
            source_sha256={str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (root / "jev_ultrafast").rglob("*") if p.suffix in {".py", ".js", ".html", ".css"}},
        )
        (args.output / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        frame()
        # Preserve measured inter-frame durations. The last frame gets a disclosed 2-second hold.
        concat = []
        for index, (timestamp, name) in enumerate(frames):
            duration = frames[index + 1][0] - timestamp if index + 1 < len(frames) else 2
            concat.extend([f"file '{name}'", f"duration {duration:.6f}"])
        concat.append(f"file '{frames[-1][1]}'")
        (args.output / "frames.ffconcat").write_text("\n".join(concat), encoding="utf-8")
        report["recorded_seconds"] = round(frames[-1][0] - frames[0][0], 6)
        report["ending_hold_seconds"] = 2
        if not passed:
            raise RuntimeError("Independent final-page check failed; publication media was not replaced.")
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "1",
            "-i", "frames.ffconcat", "-vf", "fps=12", "-c:v", "libx264", "-crf", "24",
            "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "local-demo.mp4",
        ], cwd=args.output, check=True)
        shutil.copy2(args.output / "local-demo.mp4", args.media / "local-demo.mp4")
        shutil.copy2(args.output / "inspector.png", args.media / "inspector.png")
        (args.media / "recording.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "source_sha256"}, indent=2))
    finally:
        (args.output / "recording.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if browser:
            browser.close()
        demo.close_browser()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
