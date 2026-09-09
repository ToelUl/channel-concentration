"""Bounded read-only compatibility for complete Potts postprocessing inputs."""
from pathlib import Path
from . import evidence


def input_identity(actual, current):
    """Verify every field; substitute only an audited producer's version/code hashes.

    This is a reader boundary, never a resume identity or receipt migration.
    Runtime, numerical dependencies, source binding and configuration stay exact.
    """
    if actual == current:
        return current
    if not isinstance(actual, dict) or not isinstance(actual.get("environment"), dict):
        raise ValueError("missing input producer identity")
    registry = evidence.read(Path(__file__).parent / "_data/previous_producers.json")
    version = actual["environment"].get("package_version")
    sources = registry["producers"].get(version)
    if sources is None:
        raise ValueError("unrecognized input producer version")
    expected = {**current, "environment": {**current["environment"],
                "package_version": version, "adapter_sources": sources}}
    if actual != expected:
        raise ValueError("input producer source/configuration/runtime mismatch")
    return expected
