# Contributing and reporting problems

Use English for new public documentation, issues and pull requests. The baseline's historical records remain in their original language and must not be edited in place.

## Report a reproducibility issue

Include the release or commit, selected software version, operating system, Python/dependency versions, exact command, expected result and relevant error output. Identify whether the issue concerns file integrity, installation, bounded tests, strict current-result replay, companion rendering or a fresh numerical calculation. Remove credentials and irrelevant local information from logs.

Use the repository issue tracker. Do not describe a hosted CI pass as proof of a complete large numerical rerun or final manuscript reproduction.

## Propose a change

- Keep `baseline/` unchanged. New numerical results, source changes, input selections or fitting windows require a separately versioned analysis and an explicit difference record.
- Preserve scientific definitions, normalization and numerical thresholds in presentation-only changes.
- Update the companion's source identity and figure map together when a future reviewed renderer is adopted. Do not loosen checks merely to accept a modified input.
- Describe the concrete behavior change and its validation in the pull request.

Before submitting a documentation or companion change, run the baseline verifier, companion verifier, documentation checks, and relevant tests. Rendering changes also require regenerated figures and coordinate checks. Final artwork acceptance additionally requires a visual review; CI is not that review.
