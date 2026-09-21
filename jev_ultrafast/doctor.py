"""Read-only model connection checks, without inference or opening a browser."""

import json
import os
from urllib.parse import urlsplit, urlunsplit

import httpx

from .demo import load_environment
from .model import decision_settings


def check():
    settings = decision_settings()
    report = {"provider": settings.provider, "model": settings.model, "checks": []}
    headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
    if settings.provider == "kalm":
        parsed = urlsplit(settings.base_url)
        prefix = parsed.path.removesuffix("/v1")
        health = urlunsplit((parsed.scheme, parsed.netloc, prefix + "/health", "", ""))
        try:
            response = httpx.get(health, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("status") != "ok" or data.get("model") != settings.model:
                raise ValueError("Health response does not match the configured model")
            report["checks"].append({"decision_service": "ok"})
        except (httpx.HTTPError, ValueError, AttributeError):
            report["checks"].append({"decision_service": "unavailable or wrong model; check service and SSH tunnel"})
    else:
        report["checks"].append({"decision_service": "key configured" if settings.api_key else "missing API key"})
    base = os.environ.get("TEXT_MODEL_BASE_URL", "https://api.deepseek.com/v1")
    local = urlsplit(base).hostname in {"127.0.0.1", "localhost", "::1"}
    report["checks"].append({
        "text_helper": "loopback configured" if local else (
            "key configured" if os.environ.get("TEXT_MODEL_API_KEY") else "needs a key for TYPE_TEXT"
        ),
    })
    report["note"] = "No inference was run. Health does not measure decision quality or speed."
    return report


def main():
    load_environment()
    try:
        report = check()
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print(json.dumps(report, indent=2))
    if report["checks"][0]["decision_service"] not in {"ok", "key configured"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
