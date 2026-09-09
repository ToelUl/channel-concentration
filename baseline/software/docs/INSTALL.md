# Standalone source distribution

Linux and Python 3.12 are required. Install with `python -m pip install .` or install the corresponding wheel. For bounded regression: `python -m pip install ".[test]"` then `python -m pytest tests -q -p no:cacheprovider`.

The numerical dependencies in pyproject.toml are exact pins. The full numerical-baseline bundle additionally supplies conda base builds, all transitive version pins, raw data and portable current replay helpers. Those data/tools are separate from this standalone software sdist. The original MIT license and third-party notices are included. Full manuscript acceptance is not claimed; see KNOWN_LIMITATIONS.md. Existing runtime and test bytes are unmodified.
