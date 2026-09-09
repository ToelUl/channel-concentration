"""Use the original public renderer registry without requiring private TeX files."""
from . import evidence
from .postprocess import historical_evidence, load

ANALYTIC = ("1", "2", "3", "6", "S1")


def run(project, vault, root, source, mode="publication", selectors=None):
    module = load(project, "scripts/plotting/generate_figures.py")
    selected = selectors or (list(ANALYTIC) if source == "analytic" else list(module.FIGURE_ORDER))
    if len(selected) != len(set(selected)) or any(s not in module.FIGURE_ORDER for s in selected):
        raise ValueError("unknown or duplicate figure selector")
    if source == "analytic" and any(s not in ANALYTIC for s in selected):
        raise ValueError("interacting figures require explicit current or historical numerical inputs")
    if source not in ("analytic", "historical"):
        raise ValueError("unsupported rendering source")
    if source == "historical":
        history, _ = historical_evidence(project.parent, vault)
        data_dir, evidence_dir = history / "data/reproducibility", history / "repro/evidence"
    else:
        data_dir, evidence_dir = project / "data/reproducibility", project / "repro/evidence"
    specs = [spec for spec in module.FIGURE_SPECS if spec.selector in selected]
    module.validate_selected_inputs(specs, data_dir, evidence_dir)
    root.mkdir(parents=True, exist_ok=False)
    out = root / "figures"
    out.mkdir()
    params = module.get_params(mode)
    module.configure_plotting()
    records, diagnostics = [], {}
    for spec in specs:
        context = module.PlotContext(spec, params, project, data_dir, evidence_dir)
        result = spec.renderer(context)
        try:
            module.save_figure(result.figure, spec, out)
            diagnostics.update(result.diagnostics)
        finally:
            module.plt.close(result.figure)
        inputs = [evidence.record(p, project.parent) for p in module._input_paths(spec, data_dir, evidence_dir)]
        outputs = [evidence.record(out / (spec.output_stem + suffix), root) for suffix in (".pdf", ".png")]
        records.append({"selector": spec.selector, "renderer": spec.renderer.__name__,
                        "source_role": "current" if spec.selector in ANALYTIC else "reference",
                        "generation": "analytic" if spec.selector in ANALYTIC else "postprocess",
                        "inputs": inputs, "outputs": outputs, "diagnostics": result.diagnostics})
    evidence.commit(root, "render", {"schema": "cc-repro-render/1", "status": "PASS", "mode": mode,
        "source_selection": source, "identity": evidence.context(project, {"mode": mode, "selectors": selected}),
        "producer": evidence.record(project / "scripts/plotting/generate_figures.py", project),
        "figures": records, "diagnostics": diagnostics,
        "mapping_scope": "Hash-bound original public registry; private manuscript mapping checked separately in task-local A0 inventory",
        "claim_scope": "Render and input provenance only; does not certify current interacting results or manuscript values"})
    return 0
