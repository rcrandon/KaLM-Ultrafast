# Media provenance

## Local inspector

`inspector.png` and `local-demo.mp4` capture the real inspector and a real Chrome fixture. KaLM Nano selected the article, then selected `DONE`. A separate live DOM read confirmed the article heading, article container, and URL fragment. There were two decision calls and no text-model calls.

The 79.25-second video contains 75.213 seconds of interaction at original speed, the final outcome check, and a two-second final-frame hold. Browser setup and opening the initial fixture precede the recording. Sampling is approximately twice per second; the MP4 duplicates frames at 12 fps while retaining the measured intervals. No inference wait was removed or accelerated. The capture uses the inspector's manual Choose/Execute controls, so its duration includes UI and capture overhead.

This is one successful CPU run, not a speed benchmark. The desktop also hosted another model, and the environment was not isolated. Earlier runs were faster; the recording is published with its actual duration.

Reproduce from the repository root with Chrome and KaLM running:

```powershell
uv run --env-file .env python scripts/record_inspector.py --port 8769 --output artifacts/new-recording
```

Install FFmpeg first. Use a fresh output directory and a free inspector port. The recorder owns its temporary inspector and tabs. It leaves the normal inspector on port 8766 available. Raw frames and request traces go under ignored `artifacts/`; successful publication assets go here. [recording.json](recording.json) contains the outcome, timing, call counts, and source hashes.

## Cover artwork

`cover.png` is conceptual artwork generated with the built-in image-generation tool. It is not an application screenshot or a measurement. The tool did not expose its model identifier, so no specific image model is claimed.

Prompt:

> Use case: ads-marketing. Asset type: wide GitHub README cover for an experimental local browser-control project named ULTRAFAST LOCAL, derived from Jev Ultrafast. Create one exquisitely art-directed editorial technology cover, landscape approximately 2.5:1, high resolution. Near-black graphite background, subtle fine grain, restrained warm ivory and pale acid-mint typography. Huge confident Swiss grotesk lettering on the left, exactly two lines: 'ULTRAFAST' then 'LOCAL'. Small line beneath exactly 'Observe. Choose. Act.' A small unobtrusive top eyebrow exactly 'BROWSER CONTROL / LOCAL DECISIONS'. On the right, a striking sculptural render of three thin smoked-glass rectangular browser-like planes suspended in depth, each with a few abstract tiny ivory numbered nodes, one precise vivid mint path threading through them and terminating in a small solid mint square. Clean technical elegance, architectural side lighting, extreme typographic hierarchy, generous margins, sharp high-end developer-tool visual identity. This is conceptual cover artwork, not a screenshot, not a performance chart. No fake application UI, no clocks, no benchmarks or performance promises, no robots, no brains, no lightning bolts, no neon rainbow, no gradient purple, no watermarks, no third-party logos. The typography must be exact, beautifully kerned, and fully readable when reduced to 900px wide. Restrained, memorable, publication-quality.

The hosted Jev demonstration under the parent `docs/` directory is upstream material. It is separate from these local KaLM captures.
