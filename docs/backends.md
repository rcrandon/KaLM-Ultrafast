# Choosing the decision backend

Assessment date: September 21, 2026.

**Keep KaLM-Jev Nano as the experimental backend, but neither option is a validated general Jev replacement.** Its HTTP interface and configurable input limits support the browser's finite action set. The current adapter ranks complete operation and target pairs, with descriptions suited to KaLM's retrieval training. There is no evidence that Laya is overwhelmingly better and would justify an MLX port for this project now.

KaLM now passes several complete local article and form tasks, including its own completion decision followed by an independent outcome check. Other cases still expose unwanted control changes, failure to stop, and failed recovery. Laya's typed checkpoint was evaluated through its original PyTorch runtime on earlier captured requests. It chose the wrong link with the original format, predicted premature completion with an adapted format, and truncated instructions in every tested capture. These are different evaluations, not comparative accuracy rates. See the [current evidence and reproduction steps](validation.md) and [earlier experiments](experiments.md).

The inspected inference desktop has an Intel i7-8700, 16 GB of RAM and an 8 GB GTX 1080. An existing text model occupied the GPU, so the KaLM service and Laya comparison used CPU. Neither has undergone a controlled speed comparison on this machine. Single-call timings and complete task results are recorded separately in [validation](validation.md).

| Requirement | KaLM-Jev | Laya-MLX |
| --- | --- | --- |
| Interface | HTTP `/v1/systemone` and Python `Engine.evaluate` | Python `predict` / `system_one`; no HTTP service in the inspected repository |
| Operation and target choices | Separate reranker comparisons, normalized into each question's choice distribution | All options for a question share its encoder input and decision head |
| Structured inputs | Accepts object-valued state, instructions and criterion descriptions | Serializes structured state, instructions and criterion descriptions |
| Large observations | Configurable limits; explicitly rejects excessive input | Published checkpoint budgets are 512 or 1,024 total tokens; formatting shortens text to fit |
| Runtime | PyTorch and Transformers; documented CPU and CUDA paths | Published port targets Apple Silicon; underlying MLX also supports Linux CPU and CUDA |
| Current desktop | CPU path available; GPU memory is occupied | GTX 1080 falls below the official MLX CUDA architecture requirement |

Interface details come from the inspected [KaLM schema and engine][kalm-schema] and [Laya runtime][laya-agent]. Both provide the choice, probabilities and confidence fields needed by the browser policy. Neither generates text for `TYPE_TEXT`; that still requires a separate text model. Ultrafast must continue to validate the chosen operation and its matching target against observed browser elements. [Ultrafast policy][ultrafast-model]

## Why KaLM fits the loop

KaLM accepts nested instructions and criterion descriptions, but syntactic compatibility did not make the original browser policy work. A request must name the loaded alias, such as `kalm-jev-nano`, or omit `model`; sending `jev-latest` produces HTTP 400. The service has one loaded model per process. Each choice head permits up to 255 candidates. The adapter counts the complete offered action set, including terminal choices, and rejects an oversized request instead of dropping targets. [KaLM schema][kalm-schema], [request handling][kalm-engine], [local adapter](../jev_ultrafast/kalm_policy.py)

### Adapt the question to the model

KaLM is a pointwise reranker: it scores each candidate document against the query, then normalizes those scores into a choice distribution. The [KaLM paper](https://arxiv.org/html/2606.22807v1) describes its retrieval training and encoder-decoder scoring. A generic `CLICK` description and a generic `DONE` description do not offer the same evidence as concrete browser actions.

The local adapter sends the user's exact goal as the query and offers one finite choice over supported actions such as `CLICK:4`, `SELECT:2:1`, `DONE` and `BLOCKED`. Link candidates carry visible nearby context. Native checkbox and dropdown candidates describe the local control values after that action. These descriptions do not predict navigation success or server-side effects. The completion candidate describes the current main content or observed form values.

This preserves the execution boundary: a valid choice resolves to an observed node, and the executor checks page freshness before acting. It changes the decision format. Hosted TypeSafe still uses its original operation and operation-specific target heads; KaLM chooses a joint action in one request. Inspector operation scores are summed groups of KaLM's joint probabilities, and target scores are normalized within the chosen operation. They are display summaries, not additional model predictions. [Policy implementation](../jev_ultrafast/kalm_policy.py), [response handling](../jev_ultrafast/model.py)

The agent accepts `DONE` only after checking that the page is still fresh. It does not contain a page-specific success predicate. Independent task checkers run after the model stops and verify the live DOM. This follows the public Jev loop's division between model decisions and outcome measurement. It does not reproduce Jev's proprietary training. [Upstream agent](https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/jev_ultrafast/agent.py), [local task checker](../scripts/check_local_agent.py)

The default KaLM limits are 512 tokens for state, 1,024 tokens per candidate document and 2,048 tokens for the complete decoder prompt. Ordinary browser observations can exceed the state limit. The server exposes `--query-max-length`, `--document-max-length` and `--decoder-max-length`; it checks lengths before model execution and returns HTTP 422 on overflow. Increasing the limits preserves the request but increases cost. The original rules, goal and model template must fit alongside state in the decoder budget. [Limit documentation][kalm-limits], [server options][kalm-server]

The inspected Nano checkpoint sets both encoder and decoder `max_position_embeddings` to 32,768. KaLM's backend rejects configured limits above those values. The model card's 128K description therefore does not establish a supported 128K service configuration. Upstream's public regression used 8,192 query tokens and 9,216 decoder tokens; this records one evaluated configuration, not a guarantee that large browser pages are fast or accurate. [Checkpoint configuration][nano-config], [backend validation][kalm-backend], [regression report][kalm-results]

Nano's BF16 weight file is 1,572,182,264 bytes, about 1.46 GiB. Its repository records 786,029,296 stored parameters. The advertised 270M refers to activated parameters; loading the complete checkpoint in FP32 needs approximately 2.93 GiB for parameter tensors alone. Tokenization, caches and inference require additional memory. [Pinned checkpoint files][nano-files], [model card][nano-card]

There is also a large temporary allocation in the inspected KaLM backend. It computes vocabulary logits for every decoder position before selecting the final yes/no scores. With vocabulary size 262,144, an 8,192-token sequence needs about 4 GiB of BF16 logits or 8 GiB of FP32 logits **per batch row**, before other working memory. These are tensor-size calculations, not measured peak-memory results. Large token budgets and the default batch size of four are a poor starting point on this desktop. [Scoring implementation][kalm-backend], [vocabulary size][nano-config]

Transformers supports selecting positions with `logits_to_keep` before vocabulary projection. This project implements that optimization, accounting for right padding and unequal row lengths. Four comparisons with the real Nano weights passed in FP32; maximum absolute margin error was 5.72e-6. This reduces the vocabulary-output allocation, while attention, weights and other working memory remain. [Transformers T5Gemma2 implementation][transformers-model], [local validation](validation.md)

## What a Laya port would and would not solve

MLX is no longer limited to macOS. Official documentation provides Linux CPU and CUDA installation paths. The CUDA package requires NVIDIA compute capability 7.5 or higher; the GTX 1080 is 6.1. Moving this desktop to WSL or Linux does not change that hardware limit. [MLX installation requirements][mlx-install], [NVIDIA legacy GPU table][nvidia-legacy]

Laya-MLX's inference code uses standard MLX operations, including RoPE and scaled dot-product attention. Its custom Metal experiments are outside the ordinary inference path. This makes a Linux adaptation plausible on supported hardware, but compatibility and numerical agreement still require testing. Its packaging currently declares an MLX dependency only for macOS on ARM64. [Model implementation][laya-model], [package configuration][laya-package]

For this Pascal desktop, the original Laya PyTorch implementation is a more direct starting point than porting MLX, and it was used for the CPU checks recorded above. A CUDA experiment would still need a PyTorch build with SM 6.1 support and enough free GPU memory. This recommendation concerns implementation effort; no controlled runtime comparison was performed here. [Original Laya package][laya-pytorch]

The harder issue is the browser observation. Laya's English checkpoint uses 512 tokens; multilingual and typed-decisions checkpoints use 1,024. Instructions, options and state share that budget. The formatter shortens instructions and option descriptions under a separate head budget, then truncates state to the remaining space. Raising runtime limits does not demonstrate accuracy on longer inputs. [Prompt construction][laya-format], [checkpoint descriptions][laya-readme]

Upstream Laya reports that 50 or more options are a weakness: many labels receive too little text to remain distinguishable. Its stronger typed-decisions result comes from a checkpoint tuned for four specific workflows. That result does not establish browser-action quality. A Laya browser integration would need explicit overflow checks and an evaluated strategy for reducing observations or selecting candidate groups. Such changes also alter Ultrafast's decision process. [Upstream results and limitations][laya-upstream-readme]

## What the published measurements establish

| Published measurement | Conditions | Limit of the evidence |
| --- | --- | --- |
| Laya-MLX: 13.42 ms English / 7.39 ms multilingual median | Short single question, FP16, M3 Max with 40 GPU cores | Does not predict Windows CPU, GTX 1080 or complete browser-task latency |
| KaLM Nano: 30.26 ms for 3 choices, 131.44 ms for 32, 500.91 ms for 128 | Warm candidate cache, batch size 8, H100 MIG | Different hardware and workloads from Laya; CPU results were not established |
| KaLM Nano: 122/231 correct on public JevBench regression | BF16, extended token limits | A decision benchmark, not an Ultrafast browser-task evaluation |

Sources: [Laya-MLX benchmark method and results][laya-benchmarks], [KaLM results][kalm-results]. Laya's port-fidelity checks compare its outputs with upstream Laya; they do not prove that the chosen answers are correct. KaLM's confidence measures distribution concentration and is uncalibrated by default. Neither score should replace independent verification that a browser goal was completed. [KaLM aggregation][kalm-aggregation]

## Licenses and reproducibility

Ultrafast declares MIT. Laya-MLX supplies an Apache-2.0 license and attribution notice, and its converted checkpoints declare Apache-2.0. At the inspected revision, KaLM-Jev has no repository license file or license field in its package metadata, so its code licensing is not established by those sources. The KaLM model cards declare Apache-2.0, while the T5Gemma base model declares Gemma terms. KaLM's own documentation directs users to the original publishers for applicable checkpoint terms. Keep these distinctions in dependency records; do not assign an assumed license to the KaLM-Jev service code. [Ultrafast license][ultrafast-license], [Laya code license][laya-license], [Laya checkpoint license][laya-card], [KaLM package metadata][kalm-package], [KaLM license note][kalm-aggregation], [base model card][gemma-card]

The reviewed code and model revisions are:

| Component | Revision |
| --- | --- |
| `browser-use/jev-ultrafast` | `1231850a0bf1a0c0341fe408ef1668dbbfdfac46` |
| `KaLM-Embedding/KaLM-Jev` | `ae6ed263b91fba47c5975eea782885a9054f1f5c` |
| `KaLM-Embedding/KaLM-Reranker-V1-Nano-R2` | `3902d6453ea915007dcbf88fbc8a1d7dd5f8df10` |
| `mizorewww/laya-mlx` | `fc1df62828a3fedf4d8229fdac1cbd85f1cdf337` |
| `aac6fef/laya-mlx` | `20aed815fc6acde75733882e7ec0e3f28aeb9717` |
| `NandhaKishorM/laya` | `573e5b62696ba441230cd6be71d593331b5d23af` |

GitHub records KaLM-Jev's creation on September 21, 2026, and Laya-MLX's on September 19, 2026. Their short public histories do not establish long-term maintenance. [KaLM repository metadata][kalm-metadata], [Laya-MLX repository metadata][laya-metadata]

Pin dependencies and model revisions. Reconsider the default after running identical captured browser observations through both candidates, measuring correct operation and target selection, rejected inputs, latency and peak memory, then verifying complete tasks in a controlled browser fixture.

[ultrafast-model]: https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/jev_ultrafast/model.py
[ultrafast-snapshot]: https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/jev_ultrafast/snapshot.js
[ultrafast-license]: https://github.com/browser-use/jev-ultrafast/blob/1231850a0bf1a0c0341fe408ef1668dbbfdfac46/LICENSE
[kalm-schema]: https://github.com/KaLM-Embedding/KaLM-Jev/blob/ae6ed263b91fba47c5975eea782885a9054f1f5c/src/kalm_jev/schemas.py
[kalm-engine]: https://github.com/KaLM-Embedding/KaLM-Jev/blob/ae6ed263b91fba47c5975eea782885a9054f1f5c/src/kalm_jev/engine.py
[kalm-backend]: https://github.com/KaLM-Embedding/KaLM-Jev/blob/ae6ed263b91fba47c5975eea782885a9054f1f5c/src/kalm_jev/backend.py
[kalm-server]: https://github.com/KaLM-Embedding/KaLM-Jev/blob/ae6ed263b91fba47c5975eea782885a9054f1f5c/src/kalm_jev/server.py
[kalm-package]: https://github.com/KaLM-Embedding/KaLM-Jev/blob/ae6ed263b91fba47c5975eea782885a9054f1f5c/pyproject.toml
[kalm-limits]: https://github.com/KaLM-Embedding/KaLM-Jev/blob/ae6ed263b91fba47c5975eea782885a9054f1f5c/docs/cache/README.md
[kalm-results]: https://github.com/KaLM-Embedding/KaLM-Jev/blob/ae6ed263b91fba47c5975eea782885a9054f1f5c/results/README.md
[kalm-aggregation]: https://github.com/KaLM-Embedding/KaLM-Jev/blob/ae6ed263b91fba47c5975eea782885a9054f1f5c/docs/aggregation/README.md
[nano-config]: https://huggingface.co/KaLM-Embedding/KaLM-Reranker-V1-Nano-R2/blob/3902d6453ea915007dcbf88fbc8a1d7dd5f8df10/config.json
[nano-files]: https://huggingface.co/KaLM-Embedding/KaLM-Reranker-V1-Nano-R2/tree/3902d6453ea915007dcbf88fbc8a1d7dd5f8df10
[nano-card]: https://huggingface.co/KaLM-Embedding/KaLM-Reranker-V1-Nano-R2/blob/3902d6453ea915007dcbf88fbc8a1d7dd5f8df10/README.md
[gemma-card]: https://huggingface.co/google/t5gemma-2-270m-270m
[transformers-model]: https://github.com/huggingface/transformers/blob/v5.3.0/src/transformers/models/t5gemma2/modeling_t5gemma2.py
[laya-agent]: https://github.com/mizorewww/laya-mlx/blob/fc1df62828a3fedf4d8229fdac1cbd85f1cdf337/laya_mlx/agent.py
[laya-model]: https://github.com/mizorewww/laya-mlx/blob/fc1df62828a3fedf4d8229fdac1cbd85f1cdf337/laya_mlx/model.py
[laya-format]: https://github.com/mizorewww/laya-mlx/blob/fc1df62828a3fedf4d8229fdac1cbd85f1cdf337/laya_mlx/common.py
[laya-package]: https://github.com/mizorewww/laya-mlx/blob/fc1df62828a3fedf4d8229fdac1cbd85f1cdf337/pyproject.toml
[laya-readme]: https://github.com/mizorewww/laya-mlx/blob/fc1df62828a3fedf4d8229fdac1cbd85f1cdf337/README.md
[laya-license]: https://github.com/mizorewww/laya-mlx/blob/fc1df62828a3fedf4d8229fdac1cbd85f1cdf337/LICENSE
[laya-card]: https://huggingface.co/aac6fef/laya-mlx/blob/20aed815fc6acde75733882e7ec0e3f28aeb9717/README.md
[laya-benchmarks]: https://github.com/mizorewww/laya-mlx/blob/fc1df62828a3fedf4d8229fdac1cbd85f1cdf337/BENCHMARKS.md
[laya-pytorch]: https://github.com/NandhaKishorM/laya/blob/573e5b62696ba441230cd6be71d593331b5d23af/pyproject.toml
[laya-upstream-readme]: https://github.com/NandhaKishorM/laya/blob/573e5b62696ba441230cd6be71d593331b5d23af/README.md
[mlx-install]: https://ml-explore.github.io/mlx/build/html/install.html
[nvidia-legacy]: https://developer.nvidia.com/cuda/gpus/legacy
[kalm-metadata]: https://api.github.com/repos/KaLM-Embedding/KaLM-Jev
[laya-metadata]: https://api.github.com/repos/mizorewww/laya-mlx
