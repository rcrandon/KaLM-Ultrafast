# Local validation and deployment

The implementation is experimental. The default reading task now passes with model-selected completion. A second article task fails because KaLM selects the wrong article and then chooses `DONE`. A valid API response and a confident choice are not evidence that the goal was completed.

## Verified so far

- Ultrafast was imported from commit `1231850a0bf1a0c0341fe408ef1668dbbfdfac46`.
- All 66 offline tests passed. The suite covers provider routing, authorization, request serialization, target validation, malformed responses, local text-helper requests, terminal-page freshness and inspector metadata.
- All 21 real-browser guard checks passed in an isolated headless Chrome profile. They cover stale pages, moved controls, occlusion, dropdowns, navigation and asynchronous suggestions. No model calls were used in those checks.
- A wheel and source distribution were built successfully. JavaScript syntax checks passed.
- KaLM Nano loaded on the desktop CPU. Health reports the configured model through the private SSH tunnel.
- The reduced-logit adapter passed four real-weight comparisons against upstream scoring in FP32, including unequal-length batches. Maximum absolute margin error was `5.7220458984375e-06`, within the check's tolerances. This verifies those score comparisons, not browser accuracy.
- A short three-option HTTP request selected the expected returns department. One cold request took 1,277 ms and one warm request 982 ms. These are single smoke checks, not a latency benchmark.
- The default reading task passed with one `CLICK` and one model-selected `DONE`, followed by an independent live DOM check. Agent time was 27,393 ms. No early-stop verifier or text helper participated.

## Browser policy findings

The original Ultrafast request shape made KaLM select `BLOCKED` on the local reading page even though the requested article was present. It also ranked the wrong target highest. The complete trace remains in `artifacts/local-agent.json`.

Putting the goal in the reranker's query, retaining the complete observation and rules in each question, and describing the available targets in each operation criterion made KaLM open the correct article. However, the next decision clicked back to the reading list. A four-decision run alternated between the article and the list and failed the independent outcome check. See `artifacts/local-agent-kalm-adapted.json`.

A separate experiment added current-page title and URL to the completion criterion. It predicted `DONE` before the article had been opened, so that change was rejected. Request-format experiments are preserved under `artifacts/prompt-eval/` and `artifacts/completion-eval.json`.

The adapted four-decision run took about 121 seconds of agent time while the existing desktop text model was also being tested. This is not an isolated performance measurement. It does show that the original project's 7.1-second result does not apply to this CPU configuration.

## Completion fix based on Jev's loop

The upstream [policy instructions](https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/jev_ultrafast/questions.py) require visible satisfaction of every goal condition. The [agent](https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/jev_ultrafast/agent.py) consumes the model's `DONE` choice after a freshness check. There is no extra completion classifier or page-specific stopping rule in that public implementation. Its independent example checks assess the final outcome after the agent stops.

KaLM reranks criterion descriptions independently. The first adapter gave `CLICK` a detailed target list while `DONE` remained abstract. The final adapter describes `CLICK` as opening or activating the offered visible elements, and describes `DONE` as remaining on the currently titled page only if all goal requirements are already satisfied. The original rules, full observation, operation-specific target heads and single-request loop remain intact. Hosted TypeSafe's request format is unchanged.

| Live task after the change | Model decisions | Independent result | Agent time |
| --- | --- | --- | --- |
| Open the article about finite choices | CLICK target 4, then DONE | Passed: correct article, heading, body and URL fragment | 27,393 ms |
| Open the article about network latency and page settling | CLICK target 4, then DONE | Failed: opened the finite-choices article instead | 28,152 ms |

The first final `DONE` probability was about 0.469, against 0.451 for `CLICK`. It was a narrow choice, not calibrated confidence in success. The second task is a negative completion case too: the model declared success on the wrong destination. These two runs establish a fix for the observed default-task loop, not general accuracy or a controlled speed result. Traces are `artifacts/local-agent-jev-completion.json` and `artifacts/local-agent-jev-latency.json`.

The earlier `artifacts/local-agent-verified.json` run used an independent callback to stop after a successful click. That workaround was removed from the agent and test runner after the upstream review. It is not counted as a model completion success. The current checker requires a model `done` status and a matching live DOM result, so merely visiting the right page before exhausting the step budget cannot pass.

Captured-state experiments are recorded as `artifacts/jev-completion-*.json`. Appending the full page to DONE, adding it to every operation, a separate completion choice, a criterionless Noul question, and restoring full state with completion-first instructions either stopped prematurely or continued on the completed page. Those variants were rejected. Only the concrete action-description variant passed both original before/after captures; its limited generalization is recorded above.

## Desktop runtime

The inspected desktop is Windows 10 with an i7-8700, 16 GB RAM and an 8 GB GTX 1080. The GPU had about 902 MiB free because the user's existing Qwen service was running. That service was not stopped or reconfigured.

The separate decision runtime lives at:

```text
C:\Users\User\jev-browserUse-runtime
```

It uses Python 3.12, PyTorch 2.8.0+cpu and Transformers 5.3.0. KaLM code and Nano weights are pinned in `requirements-kalm.txt` and `scripts/serve_kalm.py`. The model service uses CPU FP32, four threads, batch size one and a 64 MiB document cache. It binds only to desktop loopback port 8767.

Start an already-staged runtime and its tunnel from the laptop:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-desktop.ps1
```

The launcher refuses an occupied local port. It holds a hidden SSH session open, checks both the remote startup marker and model health, and stores logs and the SSH PID under ignored `artifacts/desktop-staging/`. The launcher does not install packages or download weights. `scripts/start-desktop-tunnel.ps1` is the separate option for forwarding to a service already running independently.

To stop this runtime, run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop-desktop.ps1`. It verifies the remote listener's Python command, staged script path and port before stopping it, then closes the recorded local forward if it still belongs to this project. `-InspectOnly` checks the remote ownership without stopping anything. This ownership check was exercised against the live listener. Closing SSH alone did not unload the remote Python process in testing. The existing port-8080 and port-18080 tunnels belong to the text model and are separate.

KaLM's measured working set after the initial smoke was about 4.08 GiB, with about 1.43 GiB of physical RAM left on the desktop. Free C: space later fell to roughly 2.5 GiB as the Windows pagefile grew. These are resource snapshots; no unrelated files or caches were removed. Avoid staging larger checkpoints until memory and disk capacity are available.

The existing text helper is `Qwen3.8-27B` at `http://127.0.0.1:8080/v1`. Field-generation checks timed out while both models were loaded, including a 120-second attempt. The client supports a configurable `TEXT_MODEL_TIMEOUT` and a per-request llama.cpp setting to disable thinking; it never substitutes a guessed field value when generation fails. A working, sufficiently responsive helper is required for `TYPE_TEXT` tasks.

## Laya checkpoint comparison

The original Laya PyTorch runtime was evaluated on the desktop with `convaiinnovations/laya-typed-decisions` at `f9ab0b228f0fc0f14d873dbc99038f135c2da1b2`. Its source revision was `573e5b62696ba441230cd6be71d593331b5d23af`. This tests Laya weights on Windows CPU; it is not a Linux MLX port or an MLX performance measurement.

| Captured browser state | Laya operation | Laya click target | Expected | Result |
| --- | --- | --- | --- | --- |
| Initial reading list, original Ultrafast format | CLICK | 2, Find a stay | CLICK, target 4 | Wrong target |
| Initial reading list, KaLM-adapted format | DONE | 4 | CLICK, target 4 | Premature completion |
| Requested article already open, adapted format | DONE | 3, unused | DONE | Correct operation |

All three inputs were truncated by the native formatter. In the original request, operation instructions retained 196 of 255 tokens and target instructions retained 100 of 337. In the adapted initial request, operation instructions retained 168 of 682 tokens and target instructions retained 100 of 759; one operation description was also shortened. The audit reconstructs native token sequences and checks that its accounting matches the formatter exactly.

The three predictions took 9,801, 2,780 and 2,799 ms after a 21,318 ms model load. These are single diagnostic calls, with no warmup or controlled machine isolation. The initial attempt to unload KaLM by closing its tunnel did not stop the remote model, so KaLM and the user's text model were still resident during this comparison. These timings must not be interpreted as a controlled speed comparison. No Laya prediction was executed in a browser.

The readout and classifier integrations work mechanically. KaLM's later completion adaptation passed the default task but failed the second one. Laya was tested on captured states before that final adaptation, not through the same final live loop. KaLM remains the experimental default for its larger input budget and existing HTTP service; these results do not establish a fair accuracy ranking. Laya needs an evaluated strategy for fitting browser observations and policy rules into its question budget before a runtime port would solve the important limitation.

Raw results are in `artifacts/laya-eval/results.json`; the checkpoint manifest is `artifacts/desktop-staging/laya-stage-manifest.json`. The Laya weights and reference source remain staged on the desktop for future experiments, but no Laya process is left running.

Reproduce captured-request evaluation with the separately installed model environment:

```powershell
python scripts/evaluate_laya.py --source PATH_TO_PINNED_LAYA_SOURCE --model-dir PATH_TO_TYPED_CHECKPOINT --input artifacts/local-agent.json --input artifacts/local-agent-kalm-adapted.json --output artifacts/laya-results.json --allow-truncation --max-cases 3
```

Omit `--allow-truncation` to reject shortened inputs, or use `--audit-only` to inspect token loss without loading model weights. This evaluator never operates a browser and never downloads checkpoints.
