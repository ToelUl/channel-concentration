#!/usr/bin/env python3
"""Build a minimal one-document arXiv source tree from canonical sources."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import tempfile
import zipfile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/cleanroom"))
from common import reject_symlinks, safe_candidate_path, candidate_run
PAPER = ROOT / "paper" / "main.tex"
SUPPLEMENT = ROOT / "supplement_numerical" / "main.tex"
WEAK_QUENCH_MODULE = ROOT / "supplement_numerical" / "weak_quench_module.tex"
MACROS = ROOT / "paper" / "macros.tex"
BBL = ROOT / "paper" / "main.bbl"
FIGURE_BASENAMES = (
    "fig1_tfim_critical_concentration",
    "fig2_scaling_and_envelope",
    "fig3_lifshitz_anisotropy_scaling",
    "fig4_xy_directional_profiles",
    "fig5_weak_quench_extraction",
    "fig6_interacting_benchmarks",
    "figS1_potts_ideal_ladder_weights",
)
RUNTIME_BASENAMES = (
    "aps10pt4-2.rtx",
    "aps4-2.rtx",
    "apsrev4-2.bst",
    "references.rev1.bib",
    "revsymb4-2.sty",
    "revtex4-2.cls",
)


def extract_supplement_body(source: str) -> str:
    begin = source.index("\\maketitle") + len("\\maketitle")
    end = source.rindex("\\end{document}")
    body = source[begin:end].strip()
    if "\\documentclass" in body or "\\begin{document}" in body:
        raise ValueError("supplement body extraction retained a document boundary")
    return body


def supplemental_transition() -> str:
    return r"""
% BEGIN NUMERICAL SUPPLEMENT
\clearpage
\onecolumngrid
\setcounter{section}{0}
\setcounter{subsection}{0}
\setcounter{equation}{0}
\setcounter{figure}{0}
\setcounter{table}{0}
\counterwithout{equation}{section}
\renewcommand{\thesection}{S\arabic{section}}
\renewcommand{\thesubsection}{S\arabic{section}.\arabic{subsection}}
\renewcommand{\theequation}{S\arabic{equation}}
\renewcommand{\thefigure}{S\arabic{figure}}
\renewcommand{\thetable}{S\arabic{table}}
\renewcommand{\theHsection}{supplement.\arabic{section}}
\renewcommand{\theHsubsection}{supplement.\arabic{section}.\arabic{subsection}}
\renewcommand{\theHequation}{supplement.\arabic{equation}}
\renewcommand{\theHfigure}{supplement.\arabic{figure}}
\renewcommand{\theHtable}{supplement.\arabic{table}}
\phantomsection
\pdfbookmark[0]{Supplemental Material}{supplemental-material}
\section*{Supplemental Material}
\begin{center}
{\large\bfseries Numerical Supplemental Material for\\
Channel concentration of critical quantum geometry}
\end{center}
""".strip()


def compose_source() -> str:
    paper = PAPER.read_text(encoding="utf-8")
    # In two-column combined output, the standalone appendix break can leave
    # acknowledgments alone in a column after upstream text grows. Keep the
    # appendix heading and let the combined document flow continuously.
    appendix_break = re.compile(r"\\newpage(?=\s*(?:%[^\n]*\n\s*)*\\appendix\b)")
    paper, appendix_break_count = appendix_break.subn("", paper)
    if appendix_break_count != 1:
        raise ValueError("expected one standalone appendix page-break anchor")
    macros = MACROS.read_text(encoding="utf-8").strip()
    supplement_source = SUPPLEMENT.read_text(encoding="utf-8")
    weak_quench_module = WEAK_QUENCH_MODULE.read_text(encoding="utf-8").strip()
    module_anchor = r"\input{weak_quench_module}"
    if supplement_source.count(module_anchor) != 1:
        raise ValueError("cannot locate a unique weak-quench module anchor")
    supplement_source = supplement_source.replace(
        module_anchor,
        "% BEGIN INLINED WEAK-QUENCH MODULE\n"
        + weak_quench_module
        + "\n% END INLINED WEAK-QUENCH MODULE",
        1,
    )
    supplement = extract_supplement_body(supplement_source)

    # The standalone Supplement uses [H] table placement through the float
    # package.  Its preamble is intentionally excluded from the one-document
    # arXiv source, so materialize that dependency in the derived paper
    # preamble without changing the canonical manuscript.
    if r"\usepackage{float}" not in paper:
        package_anchor = r"\usepackage{booktabs}"
        if paper.count(package_anchor) != 1:
            raise ValueError("cannot locate a unique combined-preamble anchor")
        paper = paper.replace(
            package_anchor,
            package_anchor + "\n" + r"\usepackage{float}",
            1,
        )

    # Import local label numbers in the combined document, preserving the
    # unlinked main/Supplement citation policy of both standalone documents.
    external = r"\externaldocument[supp-]{../supplement_numerical/main}"
    external_lines = re.findall(r"\\externaldocument(?:\[[^\]]*\])?\{[^}]+\}", paper)
    if external_lines != [external]:
        raise ValueError("expected exactly one declared paper-to-supplement externaldocument")
    paper = paper.replace(external, "", 1)
    paper = re.sub(
        r"\\(ref|eqref|pageref|autoref)(\*?)\{supp-([^}]+)\}",
        lambda match: rf"\{match.group(1)}{match.group(2)}{{{match.group(3)}}}",
        paper,
    )
    if re.search(r"\\(?:ref|eqref|pageref|autoref)\*?\{supp-[^}]+\}", paper):
        raise ValueError("combined paper retained a supplement-reference prefix")

    # In the independent Supplement, xr-hyper prefixes references into the
    # paper with `main-`. Rewrite only the label namespace in the derived
    # copy; retain the star so these references remain plain text even when
    # both texts share one PDF.
    supplement = re.sub(
        r"\\(ref|eqref|pageref|autoref)(\*?)\{main-([^}]+)\}",
        lambda match: rf"\{match.group(1)}{match.group(2)}{{{match.group(3)}}}",
        supplement,
    )
    if re.search(r"\\(?:ref|eqref|pageref|autoref)\*?\{main-[^}]+\}", supplement):
        raise ValueError("combined source retained an external-reference prefix")

    paper = paper.replace(
        r"\graphicspath{{../figures/}}",
        r"\graphicspath{{figures/}}",
        1,
    )
    paper = paper.replace(
        r"\input{macros}",
        "% BEGIN INLINED MACROS\n" + macros + "\n% END INLINED MACROS",
        1,
    )
    end_marker = "\\end{document}"
    if paper.count(end_marker) != 1:
        raise ValueError("canonical paper must contain exactly one end-document marker")
    combined = paper.replace(
        end_marker,
        supplemental_transition()
        + "\n\n"
        + supplement
        + "\n% END NUMERICAL SUPPLEMENT\n\n"
        + end_marker,
    )
    if combined.count("\\documentclass") != 1:
        raise ValueError("combined source must have exactly one document class")
    return combined.rstrip() + "\n"


def build_source_tree(output_dir: Path, *, figures_input: Path | None = None) -> None:
    reject_symlinks(output_dir)
    output_dir = output_dir.resolve()
    if output_dir == ROOT or (output_dir.is_relative_to(ROOT) and not output_dir.is_relative_to(ROOT / "build")):
        raise ValueError("arXiv output cannot replace a source directory")
    source_figures = figures_input if figures_input is not None else ROOT / "figures"
    for basename in FIGURE_BASENAMES:
        path = source_figures / f"{basename}.pdf"
        reject_symlinks(path)
        if not path.is_file():
            raise FileNotFoundError(f"declared figure input missing: {path}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arxiv-source-") as temporary:
        stage = Path(temporary) / "source"
        figure_dir = stage / "figures"
        figure_dir.mkdir(parents=True)
        (stage / "main.tex").write_text(compose_source(), encoding="utf-8")
        shutil.copy2(BBL, stage / "main.bbl")
        for basename in RUNTIME_BASENAMES:
            shutil.copy2(ROOT / "paper" / basename, stage / basename)
        for basename in FIGURE_BASENAMES:
            shutil.copy2(source_figures / f"{basename}.pdf", figure_dir / f"{basename}.pdf")

        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.copytree(stage, output_dir)


def build_zip(source_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = zip_path.with_suffix(".tmp.zip")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir).as_posix())
    temporary.replace(zip_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--figures-input", type=Path)
    parser.add_argument("--zip", type=Path, default=None)
    args = parser.parse_args()

    run = candidate_run()
    args.output_dir = safe_candidate_path(args.output_dir or run.arxiv)
    build_source_tree(args.output_dir, figures_input=args.figures_input or run.figures)
    digest = hashlib.sha256((args.output_dir / "main.tex").read_bytes()).hexdigest()
    print(f"wrote {args.output_dir}")
    print(f"main.tex sha256={digest}")
    if args.zip is not None:
        build_zip(args.output_dir, safe_candidate_path(args.zip))
        print(f"wrote {args.zip}")


if __name__ == "__main__":
    main()
