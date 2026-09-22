# Setup

[Back to the project](../README.md)

Ultrafast Local has three parts: Chrome, the lightweight Python client, and a separate decision service. A fourth service supplies text when a task needs typing. The browser and models can run on different machines.

The Windows CPU path was exercised during development. The Linux commands below follow the same environment layout but have not been validated end to end in this project. Current task accuracy and hardware measurements are in [validation](validation.md).

## 1. Install the browser client

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), Git and Google Chrome. Python 3.12 or newer is required; uv can install a compatible interpreter. Node.js is needed for the JavaScript development checks.

```text
git clone https://github.com/rcrandon/jev-ultrafast.git jev-browserUse
cd jev-browserUse
uv sync --locked
```

Copy `.env.example` to `.env` once. Keep any existing `.env`; it holds local endpoints and credentials and is ignored by Git.

```powershell
# Windows PowerShell, fresh checkout only
Copy-Item .env.example .env
```

```bash
# Linux, fresh checkout only
cp .env.example .env
```

The default decision endpoint is `http://127.0.0.1:8767/v1`, with model alias `kalm-jev-nano`. Start the model service next, or forward a service already running on another machine.

## 2. Start KaLM Nano

Install the model dependencies in a separate environment. The browser client itself does not need PyTorch. The pinned model file is about 1.46 GiB; CPU FP32 inference requires several additional GiB of memory. Check the target machine's capacity before downloading.

### Windows CPU

Run from the project directory:

```powershell
uv venv --python 3.12 .venv-kalm
uv pip install --python .venv-kalm/Scripts/python.exe torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv-kalm/Scripts/python.exe -r requirements-kalm.txt
.venv-kalm/Scripts/hf.exe download KaLM-Embedding/KaLM-Reranker-V1-Nano-R2 --revision 3902d6453ea915007dcbf88fbc8a1d7dd5f8df10 --local-dir models/KaLM-Nano
.venv-kalm/Scripts/python.exe scripts/serve_kalm.py --model-path models/KaLM-Nano --verify-readout --verification-output artifacts/readout-parity.json
```

Leave this terminal running. The service listens on `127.0.0.1:8767` after its startup checks.

### Linux CPU

```bash
uv venv --python 3.12 .venv-kalm
uv pip install --python .venv-kalm/bin/python torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv-kalm/bin/python -r requirements-kalm.txt
.venv-kalm/bin/hf download KaLM-Embedding/KaLM-Reranker-V1-Nano-R2 --revision 3902d6453ea915007dcbf88fbc8a1d7dd5f8df10 --local-dir models/KaLM-Nano
.venv-kalm/bin/python scripts/serve_kalm.py --model-path models/KaLM-Nano --verify-readout --verification-output artifacts/readout-parity.json
```

The checkpoint contains Python model code as well as weights. `requirements-kalm.txt` pins the service source, and the download pins the checkpoint revision. Read the [separate code and model license declarations](backends.md#licenses-and-reproducibility) before redistribution.

### Runtime settings

| Service option | Default | Meaning |
| --- | --- | --- |
| `--device` | `cpu` | PyTorch device |
| `--dtype` | `float32` | Model precision |
| `--threads` | `4` | CPU threads |
| `--chunk-size` | `4` | Document compression ratio; `1` retains every encoder position |
| `--query-max-length` | `4096` | Query token limit |
| `--document-max-length` | `1024` | Per-candidate token limit |
| `--decoder-max-length` | `6144` | Complete decoder prompt token limit |
| `--port` | `8767` | Loopback service port |

The service uses batch size one and a 64 MiB document cache. Requests exceeding its input limits are rejected explicitly. Larger limits cost memory and inference time; they do not establish better browser decisions.

`--verify-readout` checks the optimized final-position vocabulary projection against upstream scoring with the loaded weights before accepting requests. `--full-logits` restores upstream scoring for diagnosis. These are numerical checks, not task-accuracy checks.

For CUDA, install a PyTorch build compatible with the GPU and driver instead of the CPU wheel, then choose `--device cuda` and a supported precision. This project's live KaLM measurements used CPU. They do not validate a particular CUDA configuration.

## 3. Connect Chrome

Keep these values in `.env` for the project browser:

```dotenv
BU_CDP_URL=http://127.0.0.1:9222
BU_NAME=jev-browserUse
```

On Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-browser.ps1
```

The launcher starts headless Chrome with a profile under ignored `artifacts/chrome-profile`. If a debugging browser already answers on port 9222, the script leaves it running and uses that endpoint. Choose a different port with `-Port` and update `BU_CDP_URL` if necessary.

On Linux, launch Chrome in another terminal. Adjust the executable name if your installation uses `google-chrome-stable` or `chromium`:

```bash
google-chrome --headless=new --no-first-run --no-default-browser-check \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 \
  --user-data-dir="$(pwd)/artifacts/chrome-profile" about:blank
```

To use another Chrome session, remove the two overrides and follow [Browser Harness's connection instructions](https://github.com/browser-use/browser-harness). The project profile keeps the demo separate from everyday browsing.

## 4. Open the inspector

```text
uv run --env-file .env jev-doctor
uv run --env-file .env jev
```

Open **[http://127.0.0.1:8766](http://127.0.0.1:8766)**. The doctor checks service health and configuration without running inference. A healthy service can still make incorrect decisions.

Start with the local Reading room fixture. **Choose next** inspects one prediction; **Run automatically** executes successive decisions. Tasks that only click, select or scroll do not need the text helper. Use the [independent task checks](../CONTRIBUTING.md#live-browser-checks) to verify outcomes beyond the inspector's `DONE` status.

## Text generation

`TYPE_TEXT` calls a separate OpenAI-compatible `/chat/completions` endpoint. Configure a model that can return exactly `{"text": "value"}`:

```dotenv
TEXT_MODEL_BASE_URL=http://127.0.0.1:8080/v1
TEXT_MODEL=your-local-text-model
TEXT_MODEL_API_KEY=
TEXT_MODEL_REASONING=omit
TEXT_MODEL_TIMEOUT=120
```

An empty key is permitted only for a loopback text endpoint. Remote services require `TEXT_MODEL_API_KEY`. For llama.cpp, set `TEXT_MODEL_REASONING=llama_cpp` to disable thinking through the request's template options. `omit` sends no reasoning setting; `none` sends a reasoning-disable flag. Compatibility depends on the service.

The client rejects malformed or empty field values. It does not guess text when the helper fails. Live field generation timed out in the tested local setup and remains unvalidated; configure a responsive helper before attempting typing tasks.

## Run inference on another computer

Install the same model environment and start `serve_kalm.py` on the remote computer. It should remain bound to remote loopback. Forward it to the browser machine:

```text
ssh -N -L 127.0.0.1:8767:127.0.0.1:8767 your-user@your-desktop
```

Keep the client endpoint at `http://127.0.0.1:8767/v1`. A separately hosted text model needs its own forward. Closing a forward disconnects the client; it does not reliably unload a model process on the other computer.

### Managed Windows desktop helpers

The PowerShell helpers start and stop an **already staged** Windows runtime. They do not download weights or install dependencies. They expect this layout on the remote desktop:

```text
%USERPROFILE%/jev-browserUse-runtime/
  .venv/Scripts/python.exe
  scripts/serve_kalm.py
  jev_ultrafast/kalm_backend.py
  models/KaLM-Reranker-V1-Nano-R2-3902d6453ea915007dcbf88fbc8a1d7dd5f8df10/
```

Create the runtime environment there using the model installation steps above, naming it `.venv`, copy the two project source files into the shown locations, and download the pinned model into the shown model directory. The launcher checks the required files before starting. A different runtime root can be passed with `-RemoteRuntime`.

Store the destination in the browser machine's ignored `.env`:

```dotenv
JEV_SSH_TARGET=your-user@your-desktop
```

SSH authentication and the desktop's host key must already be configured. These helpers use noninteractive SSH with strict host-key checking.

```powershell
# Start the staged model and its forward.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-desktop.ps1

# Or forward to a service that is already running.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-desktop-tunnel.ps1

# Check which remote listener the stop helper would manage.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-desktop.ps1 -InspectOnly

# Stop the verified project model and its recorded local forward.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-desktop.ps1
```

Use one startup option at a time. The combined launcher refuses an occupied local port. Logs and the recorded forward PID live under ignored `artifacts/desktop-staging/`. The stop helper verifies the remote Python command, runtime path and port before stopping it.

## Provider configuration

| Environment setting | KaLM default | Purpose |
| --- | --- | --- |
| `DECISION_PROVIDER` | `kalm` | Select `kalm` or `typesafe` explicitly |
| `DECISION_BASE_URL` | `http://127.0.0.1:8767/v1` | Base URL; the client appends `/systemone` |
| `DECISION_MODEL` | `kalm-jev-nano` | Loaded model alias |
| `DECISION_API_KEY` | Empty | Optional authorization header |
| `DECISION_TIMEOUT` | `120` | Request timeout in seconds |
| `TEXT_MODEL_BASE_URL` | Set in `.env` | Independent text-generation endpoint |
| `TEXT_MODEL` | Set in `.env` | Text model identifier |
| `TEXT_MODEL_API_KEY` | Set in `.env` | Text-service credential, if required |
| `TEXT_MODEL_REASONING` | Provider-dependent | `omit`, `none` or `llama_cpp` override |
| `TEXT_MODEL_TIMEOUT` | `120` without a key; otherwise `25` | Text request timeout in seconds |

To use hosted Jev, set:

```dotenv
DECISION_PROVIDER=typesafe
DECISION_BASE_URL=https://api.typesafe.ai/v1
DECISION_MODEL=jev-latest
DECISION_API_KEY=your-typesafe-key
```

TypeSafe mode also recognizes `TYPESAFE_MODEL` and `TYPESAFE_API_KEY` when their generic replacements are absent. Its default decision timeout is 25 seconds. Hosted inference may incur charges. The client never switches providers automatically.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Doctor reports an unavailable service | Wait for model startup; confirm the SSH forward and the configured model alias |
| HTTP 422 | Candidate count or token limits were exceeded; inspect the request before increasing limits |
| HTTP 429 or service busy | Another decision is using the single service slot; avoid overlapping test runs |
| Browser connection fails | Confirm Chrome's debugging port matches `BU_CDP_URL` |
| Typing times out | Test the text helper separately and check its model identifier and timeout |
| Model says `DONE` on the wrong page | This is a policy failure; keep the trace and run an independent outcome check |

Raw traces can contain page text and entered values. Keep them in ignored `artifacts/`, and remove private data before sharing a reproduction.
