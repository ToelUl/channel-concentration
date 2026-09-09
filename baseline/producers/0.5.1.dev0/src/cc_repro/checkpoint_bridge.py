"""Commit original NNN checkpoints at task boundaries without changing numerics."""
import importlib
import json
from pathlib import Path
import sys
from .resources import digest
from .campaign import environment, checkpoint_backup
from . import evidence


class Paused(Exception):
    """An explicitly requested stop at a durable task boundary."""


def commit_context(project, mode):
    return {"schema": "cc-repro-nnn-commit/1", "mode": mode,
            "bridge_sha256": digest(Path(__file__)),
            "source_binding_sha256": digest(project.parent / "binding.json"),
            "adapter_environment": environment(),
            "manifest_meaning": "completed tasks only; not terminal publication qualification"}


def run(project, run_root, mode, resume, stop_after=None):
    sys.path.insert(0, str(project / "scripts/simulation"))
    original = importlib.import_module("reproduce_nnn_tfim_expensive")
    workdir = run_root / "work/nnn_tfim_expensive"
    context = commit_context(project, mode)
    marker = workdir / "cc_repro_commit_context.json"
    if resume:
        if not marker.is_file() or json.loads(marker.read_text()) != context:
            raise ValueError("NNN resume requires this adapter's original commit context; historical stores are not adopted")
        counts_manifest = evidence.read(workdir / "response-counts-manifest.json")
        if counts_manifest["context"] != context:
            raise ValueError("NNN count sidecar context mismatch")
        manifest = evidence.read(workdir / "checkpoint_manifest.json")
        expected_count_keys = {Path(r["path"]).stem for r in manifest["checkpoints"] if Path(r["path"]).stem.startswith("response_")}
        evidence.verify_keys([Path(r["path"]).stem for r in counts_manifest["files"]], expected_count_keys)
        for item in counts_manifest["files"]:
            counts = evidence.read(evidence.verify_file(workdir, item))
            checkpoint = evidence.read(workdir / "checkpoints" / (counts["task_key"] + ".json"))
            if counts["context"] != context or counts["task"] != checkpoint["task"]:
                raise ValueError("NNN count sidecar task mismatch")
        # The original validator runs in original.main before checkpoints are used.
    Base = original.Checkpoints
    original_hybrid = original.engine.hybrid_level_projector_kf
    last_counts = {}

    def capture_counts(*args, **kwargs):
        result = original_hybrid(*args, **kwargs)
        last_counts.update({"requested": kwargs["n_low_energy_eigenpairs"],
                           "nominal_eigenpairs": result["nominal_eigenpairs"],
                           "solver_returned": result["solver_eigenpairs"],
                           "guard_used": result["guard_eigenpairs"],
                           "retained_groups": result["n_levels"],
                           "source": "same unchanged engine invocation, before response_task projection"})
        return result

    class CommittedCheckpoints(Base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not self.resume:
                if list(self.directory.glob("*.json")):
                    raise ValueError("fresh NNN store is not empty")
                original.atomic_write_json(marker, context)
                self.commit()

        def commit(self):
            paths = sorted(self.directory.glob("*.json"))
            manifest = {
                "schema_version": "nnn-tfim-checkpoint-manifest/1.1.0",
                "engine_sha256": self.engine_hash,
                "config_sha256": self.config_hash,
                "solver_environment_sha256": self.environment_hash,
                "checkpoint_count": len(paths),
                "checkpoints": [{"path": p.name, "sha256": original.sha256_file(p)} for p in paths],
                "cc_repro_commit": context,
            }
            import os
            for path in paths:
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
            if self.directory.exists():
                fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(fd)
                finally: os.close(fd)
            evidence.write(workdir / "checkpoint_manifest.json", manifest)
            counts = sorted((workdir / "response-counts").glob("*.json"))
            evidence.write(workdir / "response-counts-manifest.json",
                           {"context": context, "files": [evidence.record(p, workdir) for p in counts]})

        def run(self, key, task, function):
            last_counts.clear()
            previous = self.computed_count
            result = super().run(key, task, function)
            if self.computed_count > previous:
                if last_counts:
                    evidence.write(workdir / "response-counts" / (key + ".json"),
                                   {"task": task, "task_key": key, "counts": dict(last_counts), "context": context})
                self.commit()
                checkpoint_backup(project.parent)
                if stop_after is not None and self.computed_count >= stop_after:
                    self.events.emit("adapter-paused", committed_tasks=self.computed_count)
                    raise Paused("requested checkpoint boundary reached")
            return result

    original.Checkpoints = CommittedCheckpoints
    original.engine.hybrid_level_projector_kf = capture_counts
    sys.argv = [str(project / "scripts/simulation/reproduce_nnn_tfim_expensive.py"),
                "--mode", mode, "--run-root", str(run_root),
                "--resume" if resume else "--no-resume"]
    try:
        original.main()
    except Paused as error:
        print(str(error))
        return 75
    finally:
        original.Checkpoints = Base
        original.engine.hybrid_level_projector_kf = original_hybrid
    return 0
