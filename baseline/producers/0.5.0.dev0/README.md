# cc-repro 0.5.0.dev0

Exact numerical/adaptor source for the 2026-09-09 numerical baseline.

This is the frozen producer source. Do not substitute its identity in existing receipts.

See the outer release README and docs/REPRODUCE.md for commands, environment and known limitations. Source/test/resource bytes are unchanged; release documentation is newly assembled. MIT and vendored notices are retained. This is a local development candidate, not a claim of complete manuscript reproduction.

Standalone install: `python -m pip install .`. Small regressions: `python -m pip install ".[test]"`, then `python -m pytest tests -q`. Supported runtime: Linux and Python 3.12. Original numerical dependencies are pinned in pyproject.toml.
