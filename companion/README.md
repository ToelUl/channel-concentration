# Publication companion

The current public wrapper supplies figure lookup, selected rendering, and
bounded verification for the manuscript's public companion. Its rendering
functions and seven approved PDF identities come from the author-approved S2
presentation version `2026.09.10-s2`; that label identifies the renderer and
artwork authority, not the current wrapper. The wrapper also includes the
later figure-name alignment and S3 public navigation and verification
integration (S3 is the project's public-support integration stage).
It uses the separate immutable numerical release `baseline-2026-09-09-rc1`.
Cite the exact repository commit used for companion outputs until a versioned
current-companion release is made after the author-led final local revision.

## Quick start

Run commands from the repository root. Use Linux/WSL and a separate Python 3.12.13 environment for rendering. Dependency installation requires access to the package index; rendering and verification use local files only.

```sh
python3.12 -m venv .venv-companion
. .venv-companion/bin/activate
python -m pip install -r companion/requirements.txt
python -m pip check
python -B baseline/tools/verify_release.py
python -B companion/run.py verify
python -B companion/run.py describe 4
python -B companion/run.py render --fig 4 --output build/figure-4
python -B companion/run.py render
python -B companion/run.py verify-artwork
python -B companion/run.py verify-hosted-artwork
python -B companion/run.py gallery
```

`describe` accepts a figure number (`4`), stable key (`interacting_benchmarks`), or TeX label (`fig:interacting-benchmarks`). It reports the same machine-readable `code_routes` stored in `FIGURE_MAP.json`, together with the locator and reproduction command, without requiring manuscript source or plotting packages. Each route identifies a stage, repository-relative source path, Python symbol, role, and execution class. Use the [Figure guide](../docs/FIGURE_GUIDE.md) for the clickable scientific-computation, transformation/archive, and publication-renderer route plus the evidence limits.

`render --fig` accepts one or more selectors, such as `--fig 1 2 S1`. It writes only those figures and their semantic plot-data exports to a new output directory, checks the relevant interacting or analytic artist coordinates, and records the selection in `render-receipt.json`. It does **not** assert full seven-figure artwork approval. Both artwork verification commands require a complete publication render. The default `render` still creates all seven figures.

The gallery command also needs `pdflatex` with the standard `article`, `geometry`, and `graphicx` packages. It builds a seven-page figure gallery, not the manuscript or an arXiv submission. The standard-library `verify` command works independently of the plotting dependencies.

Default rendering writes seven vector PDFs and seven PNGs to `build/companion/figures/`, together with input, coordinate-check, and rendering receipts. Selected rendering writes only the requested outputs. The gallery is `build/gallery/gallery.pdf`. Use a new output directory for another run:

```sh
python -B companion/run.py render --output build/companion-second
python -B companion/run.py gallery --figure-dir build/companion-second/figures --output build/gallery-second
```

The wrapper checks exact Python, NumPy, SciPy and Matplotlib versions, sets one BLAS/OMP thread before loading numerical libraries, verifies inputs, and refuses to overwrite an existing output directory. The requirements file also fixes plotting dependency versions. This presentation environment does not replace the stricter platform/BLAS identity checks of the numerical producers and readers.

## What is computed

Figures 1, 2, 3, 6 and S1 evaluate the existing analytic formulas or
free-fermion sums. Figures 4 and 5 read archived interacting-model tables and
existing fit coefficients. Rendering performs no interacting-model eigensolve
and no new fit. A complete seven-figure render applies sixteen interacting
coordinate/bar checks and 38 analytic coordinate checks; a selected render
runs only the relevant checks. The separate
`python -B tools/verify_scientific_contracts.py` command checks selected
physics formulas, archived evidence semantics, and the conditional R3
refinement-budget receipt independently of PDF identity. The specialist R3
checker remains directly runnable from `r3_support/`.

The Figure 4 and 5 code routes deliberately separate three operations. The
historical producer/campaign entries can perform expensive eigensolves; the
postprocessors and `baseline/tools/replay_current.py` consume archived outputs;
and `render --fig` only reads the resulting frozen tables. The Figure 5 CFT
route is a checked projection of existing evidence, not a new lattice
calculation. A code-route link therefore records provenance and execution
class; it is not an instruction to run every upstream stage.

The rendering functions and exporter retain the approved S2 implementation; the `2026.09.12-figure-names` update changes registry output filenames to match manuscript numbering. The exact predecessor is retained at commit `5a4e07dd444c7eca34d1d349d1e7d3e090b514a6`. Use `run.py` as the public entry point. The source script's direct CLI expects manuscript files; the public wrapper instead checks a source-derived, version-bound [figure map](FIGURE_MAP.json). It also rejects mismatches between figure numbers, renderer names and output filenames.

S2 adjusts graphical contrast, type size, marker presentation and legend spacing while preserving numerical arrays, normalizations and fit coefficients. All interacting Figure 4 samples remain displayed; the Figure 5 legend identifies retained ranks. [ARTWORK.json](ARTWORK.json) records the seven human-approved PDF identities. `verify-artwork` compares a local figure directory with that exact set and rejects missing, extra or different PDFs. It remains the author-side 7/7 exact check. A render's numerical/data checks alone do not imply the human approval of its output bytes.

The standard GitHub-hosted workflow runs `verify-hosted-artwork`. It still requires six non-S1 PDFs to match the approved hashes exactly. For Figure S1 it requires the complete publication render and its coordinate-check receipt, an exact approved-render PNG hash, identical plot-data structure and x coordinates, and all 450 y coordinates within `rtol=1e-11` of the frozen [approved S2 plot-data reference](reference/S1-approved-plot-data.json), with zero absolute tolerance. The reference was exported by a local seven-PDF exact render and is hash-bound in `run.py`. The observed non-AVX-512 NumPy path differs in 338 y values, with maximum relative difference about `6.064e-12`; it passes this narrow allowance. The command reports `EXACT_7_OF_7` when S1 PDF also matches, or `PORTABLE_S1_CHECK` when its PDF bytes differ. `PORTABLE_S1_CHECK` does **not** approve the newly generated S1 PDF or assert seven-PDF exact reproduction. The approved PDFs and `ARTWORK.json` are unchanged; use `verify-artwork` in the author-approved environment when exact seven-PDF identity is required.

## Figure and evidence map

| Figure | Content | Input basis |
|---|---|---|
| 1 | TFIM/XX response and concentration | Analytic formulas and free-fermion sums |
| 2 | Scaling collapse and envelope | Analytic formulas and free-fermion sums |
| 3 | Lifshitz anisotropy and scaling | Analytic formulas and free-fermion sums |
| 4 | Potts and NNN finite-size comparisons | Archived tables and fixed fit coefficients |
| 5 | Ranked response distributions | Archived ranks and lossless CFT projection |
| 6 | XY directional profiles | Analytic formulas and free-fermion sums |
| S1 | Weak-quench extraction | Analytic formulas and free-fermion sums |

Output names now match figure numbers and renderer names:

| Figure | PDF / PNG stem | Renderer |
|---|---|---|
| 1 | `fig1_tfim_critical_concentration` | `plot_fig1_tfim_critical_concentration` |
| 2 | `fig2_scaling_and_envelope` | `plot_fig2_scaling_and_envelope` |
| 3 | `fig3_lifshitz_anisotropy_scaling` | `plot_fig3_lifshitz_anisotropy_scaling` |
| 4 | `fig4_interacting_benchmarks` | `plot_fig4_interacting_benchmarks` |
| 5 | `fig5_distribution_comparisons` | `plot_fig5_distribution_comparisons` |
| 6 | `fig6_xy_directional_profiles` | `plot_fig6_xy_directional_profiles` |
| S1 | `figS1_weak_quench_extraction` | `plot_figS1_weak_quench_extraction` |

Use a fresh output directory after upgrading. Earlier commits and sealed numerical archives retain their historical filenames. The standalone supplement numbers its sole figure as 1; its shared identity and combined-manuscript number are S1. All seven approved PDF hashes remain unchanged.

[INPUTS.json](INPUTS.json) maps 42 shared input/support records to unchanged public baseline files. The small file in `inputs/cft/` is an explicitly identified schema projection. Its high-precision decimal strings and recorded agreement flags are checked against the original public source. See [the table and evidence guide](../docs/EVIDENCE_MAP.md) for the historical and analytic distinctions.

The [Figure guide](../docs/FIGURE_GUIDE.md) is the complete clickable human figure-to-code route. [FIGURE_MAP.json](FIGURE_MAP.json) is its machine-readable counterpart, and `describe` exposes the same route inventory. Route-integrity checks require all seven publication renderers, parse every referenced Python symbol, and require every direct Figure 4–5 input to have an identified producer, postprocessor, projection, or archived replay route. This page stays focused on commands, output locations, and identity checks.

## Document generation sources

`scripts/build_documents_only.py`, `scripts/packaging/build_arxiv_bundle.py`, and `scripts/cleanroom/common.py` preserve the candidate's document-generation implementation. They require the matching author's `paper/`, `supplement_numerical/`, and `figures/` trees in the original project layout. Those manuscript sources are not included in this preparation companion. Do not invoke that author-only route as a standalone public reproduction command.

The gallery command is the fully public document build tested by companion CI. Final manuscript builds, arXiv target-environment checks, and the final submission source release remain separate preparation stages.

## Scope and licensing

Input and coordinate checks do not certify spectral completeness or remove historical evidence gaps. Human artwork approval applies to the exact S2 PDF hashes; the identity check verifies whether local outputs match that approved set. Potts retained ordering and full-spectrum ordering have different certified ranges; conditional enclosures keep their spectral premises. See the [baseline limitations](../baseline/docs/KNOWN_LIMITATIONS.md).

The newly distributed project scripts, wrapper, documentation, and project-generated schema projection are covered by the repository MIT License. Installed dependencies retain their own licenses. No manuscript text is distributed or relicensed by this companion.
