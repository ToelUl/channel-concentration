"""Public renderer/input registry check; no TeX validation or figure rendering."""
import importlib.util
import sys
from .resources import digest


def check(project):
    producer = project / "scripts/plotting/generate_figures.py"
    spec = importlib.util.spec_from_file_location("cc_original_figure_registry", producer)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # Required by original dataclass annotations.
    try:
        spec.loader.exec_module(module)
        specs = module.FIGURE_SPECS
        selectors = [s.selector for s in specs]
        if selectors != ["1", "2", "3", "4", "5", "6", "S1"]:
            raise ValueError("original seven-figure registry identity mismatch")
        if len({s.output_stem for s in specs}) != len(specs):
            raise ValueError("duplicate original figure output alias")
        records = []
        for item in specs:
            if not callable(item.renderer):
                raise ValueError(f"missing renderer for {item.selector}")
            inputs = [project / "data/reproducibility" / n for n in item.data_inputs]
            inputs += [project / "repro/evidence" / n for n in item.evidence_inputs]
            records.append({"selector": item.selector, "key": item.key,
                            "renderer": item.renderer.__name__, "output_stem": item.output_stem,
                            "inputs": [{"path": p.relative_to(project).as_posix(), "sha256": digest(p)} for p in inputs]})
        return {"status": "PASS", "scope": "original renderer and input inventory only",
                "producer_sha256": digest(producer), "figures": records,
                "manuscript_mapping_checked": False, "figures_rendered": False}
    finally:
        sys.modules.pop(spec.name, None)
