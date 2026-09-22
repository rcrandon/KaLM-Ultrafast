# Security

Ultrafast Local is an experimental browser agent. Its guards validate observed targets and page freshness; they do not guarantee that the model's choice is correct or that page content is trustworthy.

The model service and project Chrome debugging endpoint are intended for loopback access. Use SSH forwarding when inference runs on another machine. Keep `.env`, browser profiles, keys and raw traces private. A trace can include page text and values entered into fields.

## Reporting a vulnerability

Use the repository's [private vulnerability reporting page](https://github.com/rcrandon/jev-ultrafast/security/advisories/new) if it is enabled. If that page is unavailable, open an issue requesting a private contact route without including exploit details, credentials or private page contents. No response-time commitment is currently published.

Useful reports identify the affected revision, the execution path, a minimal reproduction and the observed impact. Use a local fixture and dummy values where possible. Do not upload another person's browser session, tokens or private model endpoint.

## Relevant boundaries

- Browser mutations resolve to observed nodes; model responses are not executed as code.
- A separate text helper supplies field values and its output is validated before typing.
- The optional KaLM checkpoint includes Python code. Review its pinned source and model terms before installation.
- Hosted TypeSafe and remote text endpoints receive the configured request content. Select providers and browser profiles appropriate for the pages you intend to use.
- The local server is a development tool, not a multi-user authenticated service.
