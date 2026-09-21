# Ultrafast with KaLM-Jev

Ultrafast's browser agent, refactored to use **KaLM-Jev Nano** for local decisions. Chrome stays on the laptop; the decision service can run locally or on the desktop through SSH. An independent OpenAI-compatible model supplies values only for `TYPE_TEXT`.

The starting point is [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast) at `1231850a0bf1a0c0341fe408ef1668dbbfdfac46`. Its indexed elements, operation-specific target questions, page freshness checks and guarded execution remain in place. Hosted TypeSafe is available as an explicit configuration choice. A failed local request never switches to a paid endpoint.

**Why KaLM:** its HTTP interface accepts Ultrafast's structured questions, and its configurable context budget accommodates larger browser observations. Laya remains a plausible candidate for short decisions, including through Linux MLX or its original PyTorch runtime. Its short context and option-description budgets are the larger obstacles for this browser loop. See the [comparison and pinned sources](docs/backends.md). This recommendation does not claim that KaLM wins a browser accuracy or speed benchmark.

## Run the inspector

From this directory in PowerShell:

```powershell
uv sync --locked
# On a fresh checkout only. Keep an existing .env.
Copy-Item .env.example .env
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-browser.ps1
uv run --env-file .env jev-doctor
uv run --env-file .env jev
```

Open [the inspector](http://127.0.0.1:8766). The default Reading room task uses a local fixture. **Choose next** lets you inspect a decision; **Run automatically** executes the loop. A `DONE` prediction still needs independent outcome verification.

The working `.env` on this machine is already configured for KaLM at `127.0.0.1:8767`, the existing desktop Qwen helper at `127.0.0.1:8080`, and the isolated Chrome profile at port 9222. Preserve it. Both model services are reached through loopback SSH forwards. The doctor checks service health without running inference.

For the isolated browser, include these settings in `.env` before launching with `--env-file`:

```dotenv
BU_CDP_URL=http://127.0.0.1:9222
BU_NAME=jev-browserUse
```

`start-browser.ps1` launches headless Chrome with a project-owned profile under ignored `artifacts/chrome-profile`. The inspector shows screenshots. To use your normal Chrome profile instead, remove those two overrides, enable remote debugging in Chrome, and follow Browser Harness's connection prompts. Credentials, model files and raw traces stay out of Git.

## Decision service

The browser client has no PyTorch dependency. Install the model runtime separately, on the desktop or locally. For a Windows CPU environment:

```powershell
uv venv --python 3.12 .venv-kalm
uv pip install --python .venv-kalm/Scripts/python.exe torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv-kalm/Scripts/python.exe -r requirements-kalm.txt
.venv-kalm/Scripts/hf.exe download KaLM-Embedding/KaLM-Reranker-V1-Nano-R2 --revision 3902d6453ea915007dcbf88fbc8a1d7dd5f8df10 --local-dir models/KaLM-Nano
.venv-kalm/Scripts/python.exe scripts/serve_kalm.py --model-path models/KaLM-Nano --verify-readout --verification-output artifacts/readout-parity.json
```

The pinned checkpoint includes Python model code as well as weights. The separate service installs KaLM-Jev at a fixed source revision. The [comparison](docs/backends.md) records the distinct code and checkpoint licensing declarations; KaLM-Jev's repository has no explicit code license at the inspected revision.

The service binds to `127.0.0.1:8767`, uses one CPU batch row, four threads, a 64 MiB document cache, 4,096 state tokens, 1,024 candidate tokens and 6,144 decoder tokens. Inputs that exceed these limits fail explicitly. No browser state or target list is silently discarded. Raise token limits only after checking memory and latency.

The project server projects vocabulary scores only at the final nonpadding positions. `--verify-readout` compares these margins with upstream full-sequence scoring using the loaded weights before accepting requests, including unequal-length batches. `--full-logits` selects upstream scoring for diagnosis. This reduces the temporary vocabulary output allocation; it does not eliminate the cost of reranking every candidate or prove task accuracy.

For CUDA on a suitable GPU, install a compatible PyTorch build and use `--device cuda --dtype float16` or a supported `bfloat16` configuration. This desktop's GTX 1080 is occupied by an existing model. The staged KaLM service uses CPU and leaves that process running.

Open a KaLM tunnel on the laptop if the remote service is already running and no forward is active:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-desktop-tunnel.ps1
```

The script defaults to the existing desktop SSH destination. It forwards laptop port 8767 to the desktop loopback port. Ctrl+C closes this foreground tunnel. It does not start the remote model or alter the existing port 8080 text-model tunnel. See [validation and deployment notes](docs/validation.md) for the staged runtime's paths and measured results.

## Configuration

| Setting | Default | Meaning |
| --- | --- | --- |
| `DECISION_PROVIDER` | `kalm` | `kalm` or `typesafe`; no automatic fallback |
| `DECISION_BASE_URL` | `http://127.0.0.1:8767/v1` | Base URL; the client adds `/systemone` |
| `DECISION_MODEL` | `kalm-jev-nano` | Must match the service's loaded model |
| `DECISION_API_KEY` | Empty for KaLM | Optional authorization header; omitted when empty |
| `DECISION_TIMEOUT` | `120` for KaLM | Request timeout in seconds; TypeSafe defaults to 25 |
| `TEXT_MODEL_BASE_URL` | Set in `.env` | Independent OpenAI-compatible text endpoint |
| `TEXT_MODEL`, `TEXT_MODEL_API_KEY` | Set in `.env` | Model name and credential for text generation |
| `TEXT_MODEL_REASONING` | Provider-dependent | `none` disables reasoning; `omit` omits vendor-specific reasoning fields |

An unauthenticated text helper is allowed only at a loopback host. The current desktop helper uses `Qwen3.8-27B`, `http://127.0.0.1:8080/v1`, an empty key and `TEXT_MODEL_REASONING=omit`. Text must still parse as exactly `{"text": "value"}` before execution. Configure a different helper if the chosen model cannot follow that contract.

To opt into the original hosted decision backend, set `DECISION_PROVIDER=typesafe`, `DECISION_BASE_URL=https://api.typesafe.ai/v1`, `DECISION_MODEL=jev-latest`, and `DECISION_API_KEY` to your TypeSafe key. When generic settings are absent, TypeSafe mode also recognizes the original `TYPESAFE_MODEL` and `TYPESAFE_API_KEY` variables. Live hosted calls may incur charges.

## Library and checks

```python
from jev_ultrafast import Agent

with Agent("https://en.wikipedia.org/wiki/Main_Page", "Open the article about Ada Lovelace.") as agent:
    for state in agent.run():
        print(state["elapsed_ms"], state["status"])
```

Run scripts with `uv run --env-file .env python path/to/script.py` so browser settings load before Browser Harness is imported.

```powershell
uv run ruff check .
uv run pytest
node --check jev_ultrafast/static/app.js
node --check jev_ultrafast/snapshot.js
uv build
uv run --env-file .env python scripts/check_guards.py
uv run --env-file .env python scripts/check_local_agent.py
```

Unit tests run without network calls. The guard check exercises real local controls without model calls. The local-agent check calls the configured loopback KaLM service, permits at most four decisions by default, and checks the rendered article independently. Its trace is saved under ignored `artifacts/` whether it passes or fails.

Shadow roots, frames, canvas, uploads, popup tabs, nested scrolling and arbitrary keyboard widgets remain outside the upstream MVP. The upstream video and timing results describe the hosted Jev baseline, not this KaLM configuration. They are preserved in the [original README](docs/upstream-readme.md) and [upstream performance notes](docs/performance.md).
