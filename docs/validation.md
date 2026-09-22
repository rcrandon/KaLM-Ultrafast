# Validation

The joint-action KaLM adapter completes all three local article tasks and the two-setting preferences task. Two of seven complete-task checks still fail: a digest-only goal changes an unrelated theme, and an already-correct settings goal does not stop. Recovery from a wrong article also fails in captured-state checks. This is a working experimental policy, not demonstrated parity with hosted Jev.

## Verified implementation

- **82 offline tests passed** on both Python 3.13 and a clean Python 3.12 installation. These cover response validation, provider routing, native control effects, target mapping, freshness, and text-helper contracts. No model calls are made by the unit tests.
- **27 real Chrome guard checks passed**, including moving or replaced targets, obstructed clicks, fieldset context changes, form-scoped radio groups, dropdowns, and asynchronous suggestions.
- Python lint, JavaScript syntax, a source distribution, and a wheel passed locally. A Windows/Ubuntu GitHub Actions workflow is included; it has not been run remotely by this task.
- Four real-weight reduced-logit comparisons passed against upstream FP32 scoring. Maximum absolute margin error was `5.7220458984375e-06`. This checks numerical agreement, not browser accuracy.
- The published inspector recording passed an independent final-page check: correct article heading, article container, URL fragment, and a model-selected `DONE`. [Recording metadata](media/recording.json).

## Complete browser tasks

Each task starts from a fresh local fixture, receives one natural-language goal, and allows at most four decisions. Passing requires both model completion and a separate live DOM check. The expected fixture values live in the test scripts, not in the agent. These are development examples used while improving the adapter, not a held-out benchmark.

| Goal | Model operations | Final outcome | Result |
| --- | --- | --- | --- |
| Open the finite-choices article | CLICK, DONE | Correct article | Pass |
| Open the latency article | CLICK, DONE | Correct article | Pass |
| Open the confidence article | CLICK, DONE | Correct article | Pass |
| Enable the weekly digest | CLICK, SELECT, SELECT, SELECT | Digest enabled; unrelated theme changed; no completion | Fail |
| Change theme to Dark | SELECT, DONE | Dark selected; digest unchanged | Pass |
| Enable the digest and select Dark | SELECT, CLICK, DONE | Both requested settings applied | Pass |
| Keep digest disabled and theme Light | SELECT, SELECT, SELECT, SELECT | Original values restored after unnecessary changes; no completion | Fail |

The recorded development suite took approximately 8.2 to 16.9 seconds per task. A separate real inspector recording took 74.659 seconds of agent time and produced a 79.25-second video including UI/capture overhead, final verification, and an ending hold. The machine also hosted another model; cache state and resource contention were not controlled. These runs establish observed behavior and must not be presented as a speed benchmark.

[Public result summary](results/local-validation.json) includes failures and source hashes. Raw request/response traces stay in ignored `artifacts/` because traces from other tasks can contain private page content.

Reproduce the complete tasks with Chrome and the local KaLM service running:

```powershell
uv run --env-file .env python scripts/check_local_agent.py --article choices
uv run --env-file .env python scripts/check_local_agent.py --article latency
uv run --env-file .env python scripts/check_local_agent.py --article uncertainty
uv run --env-file .env python scripts/check_preferences.py --case digest
uv run --env-file .env python scripts/check_preferences.py --case theme
uv run --env-file .env python scripts/check_preferences.py --case both
uv run --env-file .env python scripts/check_preferences.py --case already
```

Known failing cases deliberately exit with a nonzero status. They are live diagnostic checks and are not represented as passing CI tests.

## Why the adapter changed

[Upstream Jev](https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/jev_ultrafast/agent.py) asks the model for an operation and operation-specific targets, then checks freshness before execution. Its `DONE` instruction requires every goal requirement to be satisfied. The public code does not include an additional hidden completion algorithm.

[KaLM](https://github.com/KaLM-Embedding/KaLM-Jev/tree/ae6ed263b91fba47c5975eea782885a9054f1f5c) scores candidate documents independently. With the original Ultrafast request format, it chose the wrong targets, declared completion prematurely, or navigated back after opening the correct article. Its retrieval training is described in the [KaLM paper](https://arxiv.org/html/2606.22807v1).

The current adapter makes each candidate a concrete supported action:

- The original user goal is the retrieval query.
- Link candidates carry visible nearby card or row text.
- Native checkbox, radio, and dropdown candidates describe proposed local control values. Radio projections preserve group exclusivity. Arbitrary ARIA widgets are not assumed to behave like native controls.
- `DONE` competes in the same head. Its document contains current control values for forms, or the main heading and direct noninteractive paragraphs for content pages. Navigation-card descriptions are excluded from that content summary.
- The selected operation and target come from the validated joint action ID. Inspector operation scores are summed group probabilities; target scores are conditional within the selected group. They are not separate KaLM predictions.

This is an intentional retrieval representation, not a full DOM serialization. KaLM's scored request does not include all page text or recent action history; those remain in the recorded observation. Broader context variants worsened the tested decisions. TypeSafe continues to receive its original full structured observation and separate heads. Candidate or token overflow produces an error rather than silently shrinking the offered choices.

No site-specific completion callback, hardcoded task plan, extra planner, or forced test-success rule is used in the agent. The model service remains on its original compression ratio of four. Compression was not established as the fix.

## Partial completion and recovery

The captured-state check separates action selection from browser execution. It includes initial and completed forms, partially satisfied goals, unrelated controls, correct article pages, and wrong article pages:

```powershell
uv run --env-file .env python scripts/check_policy_matrix.py
```

The expected actions are fixed in the diagnostic fixture code. A `BLOCKED` response on a wrong article is counted as a failure when a visible navigation link could recover. A valid response schema or a concentrated probability distribution never substitutes for the expected outcome. See the public summary for every case, including failures.

## Runtime and alternatives

Measured decision runtime: Windows 10, i7-8700, 16 GB RAM, Python 3.12, PyTorch 2.8.0+cpu, Transformers 5.3.0, CPU FP32, four threads, one batch row, 64 MiB document cache, and KaLM Nano R2 revision `3902d6453ea915007dcbf88fbc8a1d7dd5f8df10`. The existing GPU text service was left running. Model weights and deployment paths are excluded from the repository.

The existing text helper timed out during live tests. Mocked text-helper contracts and real browser typing guards pass, but end-to-end field generation is not yet validated. Configure a responsive helper before using typing tasks.

Laya's typed checkpoint was evaluated through its original PyTorch implementation on three earlier captured requests. It selected a wrong target or premature completion on the initial page, and all three requests were truncated. Those calls were neither a Linux MLX test nor a controlled speed comparison with this final KaLM adapter. [Backend assessment and pinned sources](backends.md).

[Earlier experiments](experiments.md) retain the unsuccessful adapters and runtime findings. Hosted Jev's upstream footage and timings remain separate in [the archived README](upstream-readme.md).
