# Contributing

Help make the browser's decisions measurably better. A small reproducible failure is more useful than a claim that a model is generally reliable.

Read [the README](README.md), [AGENTS.md](AGENTS.md) and [current validation](docs/validation.md) before changing the loop. Use the [setup guide](docs/setup.md) for local inference and browser configuration.

## Development checks

```text
uv sync --locked
uv run ruff check .
uv run pytest
node --check jev_ultrafast/static/app.js
node --check jev_ultrafast/snapshot.js
uv build
```

The unit tests use mocked services and do not call paid APIs. The [CI workflow](.github/workflows/checks.yml) runs these checks on Windows and Ubuntu without model weights, browser sessions or credentials. A passing offline suite verifies those contracts; it does not establish browser-task accuracy.

## Live browser checks

Start the isolated Chrome profile before running the guard check:

```text
uv run --env-file .env python scripts/check_guards.py
```

This exercises real controls without model calls. For local KaLM task checks, start the loopback decision service as well:

```text
uv run --env-file .env python scripts/check_local_agent.py --article choices --output artifacts/article-choices.json
uv run --env-file .env python scripts/check_local_agent.py --article latency --output artifacts/article-latency.json
uv run --env-file .env python scripts/check_local_agent.py --article uncertainty --output artifacts/article-uncertainty.json
uv run --env-file .env python scripts/check_preferences.py --case both --output artifacts/preferences-both.json
uv run --env-file .env python scripts/check_preferences.py --case digest --output artifacts/preferences-digest.json
uv run --env-file .env python scripts/check_preferences.py --case theme --output artifacts/preferences-theme.json
uv run --env-file .env python scripts/check_preferences.py --case already --output artifacts/preferences-already.json
```

Run these sequentially against the single-slot service. The model must choose `DONE`, and a separate check must confirm the rendered result. Each script saves its trace whether the task passes or fails. Some cases currently fail; preserve those results alongside improvements.

## Change the policy without hiding failures

- Keep the input a natural-language goal. Avoid site-specific plans, hardcoded field strings or fixture names inside the policy.
- Offer only supported actions against observed elements. Model output must never become selectors, coordinates or executable code.
- Preserve freshness and target checks. Never retry a browser mutation automatically.
- Keep the configured provider explicit. Local failures must not switch to a paid service.
- Compare identical observations when testing request formats. Include completed pages, wrong destinations, unrelated controls and already-satisfied goals.
- Separate model-selected completion from independent verification. Record unwanted side effects, even when the requested setting was reached.

When testing model changes, include the source and checkpoint revisions, request format, runtime settings, hardware, step budget and expected result. Report failed cases and any input truncation. A narrower fixture-specific success should not become a general reliability claim.

## Pull requests

Describe the problem, resulting behavior and checks you ran. For a policy change, include a minimal local fixture or a sanitized reproduction and the before/after outcome. For a documentation change, verify commands and relative links. Keep screenshots tied to actual runs, and preserve original playback speed in demonstration footage.

Keep credentials, model files, browser profiles and raw private traces out of Git. `artifacts/` is the default location for local recordings and evaluation output. Share only reviewed, sanitized evidence. Preserve upstream attribution and distinguish the project's MIT license from optional runtime and checkpoint terms.
