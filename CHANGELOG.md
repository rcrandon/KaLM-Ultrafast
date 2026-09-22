# Changelog

## Unreleased

### Local decisions

- Added an explicit KaLM-Jev provider while retaining hosted TypeSafe as an opt-in alternative.
- Adapted KaLM requests to choose grounded operation and target pairs, with local context and observed control-state effects.
- Added a separate pinned Nano runtime and final-position vocabulary projection, with real-weight comparisons against upstream scoring.
- Added loopback service diagnostics and Windows browser and SSH runtime helpers.
- Added independent article and preference outcome checks and documented failures as well as successes.

### Publication preparation

- Reworked the README around the local inspector, setup, evaluation evidence and backend comparison.
- Added reproducible setup instructions, contribution and security guidance, issue templates and offline CI for Windows and Ubuntu.
- Separated local media and measurements from the archived hosted Jev demonstration.

Based on [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast) at `1231850a0bf1a0c0341fe408ef1668dbbfdfac46`. These changes are unreleased; the package retains its existing `0.1.0` development version.
