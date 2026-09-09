# Publication companion

Version `2026.09.10-s1` provides the presentation code for the R3.7 public-aligned preparation candidate. It uses the immutable numerical release `baseline-2026-09-09-rc1`. Final scientific and artwork review is still pending; this is not a final submission release.

## Quick start

Run commands from the repository root. Use Linux/WSL and a separate Python 3.12.13 environment for rendering. Dependency installation requires access to the package index; rendering and verification use local files only.

```sh
python3.12 -m venv .venv-companion
. .venv-companion/bin/activate
python -m pip install -r companion/requirements.txt
python -m pip check
python -B baseline/tools/verify_release.py
python -B companion/run.py verify
python -B companion/run.py render
python -B companion/run.py gallery
```

The gallery command also needs `pdflatex` with the standard `article`, `geometry`, and `graphicx` packages. It builds a seven-page figure gallery, not the manuscript or an arXiv submission. The standard-library `verify` command works independently of the plotting dependencies.

Rendering writes seven vector PDFs and seven PNGs to `build/companion/figures/`, together with input, coordinate-check, and rendering receipts. The gallery is `build/gallery/gallery.pdf`. Use a new output directory for another run:

```sh
python -B companion/run.py render --output build/companion-second
python -B companion/run.py gallery --figure-dir build/companion-second/figures --output build/gallery-second
```

The wrapper checks exact Python, NumPy, SciPy and Matplotlib versions, sets one BLAS/OMP thread before loading numerical libraries, verifies inputs, and refuses to overwrite an existing output directory. The requirements file also fixes plotting dependency versions. This presentation environment does not replace the stricter platform/BLAS identity checks of the numerical producers and readers.

## What is computed

Figures 1, 2, 3, 6 and S1 evaluate the existing analytic formulas or free-fermion sums. Figures 4 and 5 read archived interacting-model tables and existing fit coefficients. Rendering performs no interacting-model eigensolve and no new fit. Sixteen checks compare actual plotted coordinates and bars with the archived inputs.

The original rendering implementation is byte-preserved in `scripts/plotting/generate_figures.py`. Use `run.py` as the public entry point. The original script's direct CLI expects manuscript files; the public wrapper instead checks a source-derived, version-bound [figure map](FIGURE_MAP.json). It calls the same renderer functions, parameter presets and exporter without changing their mathematics or visual settings.

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

Legacy output filenames are retained. In particular, current Figure 4 uses `fig6_interacting_benchmarks`, current Figure 5 uses `figS1_potts_ideal_ladder_weights`, current Figure 6 uses `fig4_xy_directional_profiles`, and Figure S1 uses `fig5_weak_quench_extraction`. Use `FIGURE_MAP.json`, not filename numbers, to locate the intended figure.

[INPUTS.json](INPUTS.json) maps 42 shared input/support records to unchanged public baseline files. The small file in `inputs/cft/` is an explicitly identified schema projection. Its high-precision decimal strings and recorded agreement flags are checked against the original public source. See [the table and evidence guide](../docs/EVIDENCE_MAP.md) for the historical and analytic distinctions.

## Document generation sources

`scripts/build_documents_only.py`, `scripts/packaging/build_arxiv_bundle.py`, and `scripts/cleanroom/common.py` preserve the candidate's document-generation implementation. They require the matching author's `paper/`, `supplement_numerical/`, and `figures/` trees in the original project layout. Those manuscript sources are not included in this preparation companion. Do not invoke that author-only route as a standalone public reproduction command.

The gallery command is the fully public document build tested by companion CI. Final manuscript builds, arXiv target-environment checks, and the final submission source release remain separate preparation stages.

## Scope and licensing

Input and coordinate checks do not certify spectral completeness, remove historical evidence gaps, or approve publication artwork. Potts retained ordering and full-spectrum ordering have different certified ranges; conditional enclosures keep their spectral premises. See the [baseline limitations](../baseline/docs/KNOWN_LIMITATIONS.md).

The newly distributed project scripts, wrapper, documentation, and project-generated schema projection are covered by the repository MIT License. Installed dependencies retain their own licenses. No manuscript text is distributed or relicensed by this companion.
