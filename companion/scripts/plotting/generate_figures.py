#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate every figure in current manuscript order from one safe entry point.

Use --list or --describe <selector|stable-key|TeX-label> to locate a figure.
Public plot_fig* functions follow the CURRENT manuscript order below.  Their
legacy PDF/PNG filenames are intentionally not renumbered: FIGURE_SPECS is the
single runtime authority for selector, renderer, TeX binding, and output alias.
Each renderer returns a FigureResult; only the common exporter writes files.

Current manuscript order:

  Fig. 1  TFIM--XX response scale, carrier ladders, and concentration
  Fig. 2  TFIM scaling collapse and envelope-amplitude formula
  Fig. 3  Lifshitz anisotropy and scaling collapse
  Fig. 4  Potts and NNN-TFIM finite-size comparisons
  Fig. 5  Potts and NNN-TFIM ranked response distributions
  Fig. 6  XY-plane directional channel-concentration profiles
  Fig. S1 Weak one-sided quench extraction of K_F

Figures 1--3, 6, and S1 are evaluated analytically or with free-fermion sums.
Figures 4 and 5 consume released or hash-bound derived interacting-model
tables; no interacting exact diagonalization is performed by this plotting
program.  Every target writes a vector PDF and a 300-dpi PNG from the same
Matplotlib figure instance.

Main conventions
----------------
For the XY chain in the BdG representation,

    H_k = (h - cos k) sigma^z + gamma sin k sigma^x,

with positive Neveu--Schwarz momenta

    k_n = (2n+1) pi / L,   n = 0, ..., L/2 - 1.

The planar d-vector implies a rank-one per-mode metric:

    g^{(k)}_{ab} = (1/4) (partial_a theta_k)(partial_b theta_k),

and the channel weights in tangent direction y=(y^h, y^gamma) are

    x_k(y) = (1/4) ( y^h partial_h theta_k + y^gamma partial_gamma theta_k )^2.

Then

    P2 = sum_k x_k,
    P4 = sum_k x_k^2,
    K_F = P4 / P2^2.

Diagnostics
-----------
For each full run, the script prints the requested numerical diagnostics:

    Phi(0)
    KFcrit_p(2)
    Psi(0)
    K_F(h_c, L_max)
    max |R(delta)-K_F| at smallest delta
    directional K_F extrema and anisotropy
    max |R(delta)-K_F| at smallest delta
"""

from __future__ import annotations

import argparse
import csv
import json
import inspect
import re
import sys
import math
import os
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, TYPE_CHECKING

import numpy as np

from scipy.special import zeta

if TYPE_CHECKING:
    import matplotlib.pyplot as plt


# -----------------------------------------------------------------------------
# Plot style
# -----------------------------------------------------------------------------
PLOT_STYLE = {
    # Use STIX + embedded TrueType fonts.  This avoids the glyph-encoding
    # problems that can occur when Computer Modern mathtext is embedded into
    # PDF figures and then included in a LaTeX manuscript.
    "font.family": "STIXGeneral",
    "mathtext.fontset": "stix",
    "pdf.fonttype": 42,
    # Disable version-sensitive Flate compression.  With SOURCE_DATE_EPOCH
    # fixed above, this makes weak-quench and the other vector PDFs stable
    # across repeated runs of the pinned Matplotlib environment.
    "pdf.compression": 0,
    "ps.fonttype": 42,
    "font.size": 9,
    "axes.labelsize": 9,
    "axes.titlesize": 9,
    "legend.fontsize": 7.5,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "axes.linewidth": 0.8,
    "lines.linewidth": 1.3,
    "savefig.dpi": 300,
    "figure.dpi": 150,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "legend.frameon": False,
    "axes.unicode_minus": False,
}

_PLOTTING_READY = False


def configure_plotting() -> None:
    """Initialize graphics only for rendering; navigation must not build a cache."""
    global plt, _PLOTTING_READY
    if _PLOTTING_READY:
        return
    # Same original metadata/font/export settings, now initialized lazily.
    os.environ.setdefault("SOURCE_DATE_EPOCH", "1785542400")
    os.environ.setdefault(
        "MPLCONFIGDIR", str(Path(__file__).resolve().parents[2] / "build" / "matplotlib"),
    )
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update(PLOT_STYLE)
    _PLOTTING_READY = True


# Wong color-blind-safe palette
C = {
    "blue":   "#0072B2",
    "orange": "#E69F00",
    "green":  "#009E73",
    "red":    "#D55E00",
    "purple": "#CC79A7",
    "sky":    "#56B4E9",
    "black":  "#000000",
    "gray":   "#666666",
}

COL = 3.375   # PRB single-column width (in)
WIDE = 6.9    # PRB double-column width (in)

FREE_ISING = 2.0 / 3.0


# -----------------------------------------------------------------------------
# Figure identity and renderer interface (no numeric export IDs)
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class FigureSpec:
    """One authoritative binding; legacy output_stem is not a figure number.

    documents contains (document source, displayed number) pairs.  S1 is a
    CLI selector and combined-preprint number, but is Figure 1 in the standalone
    Numerical Supplement.  tex_source locates the actual figure environment.
    """

    key: str
    selector: str
    title: str
    renderer: Callable[[PlotContext], FigureResult]
    output_stem: str
    tex_label: str
    tex_source: str
    documents: tuple[tuple[str, str], ...]
    panels: tuple[tuple[str, str], ...]
    data_inputs: tuple[str, ...] = ()
    evidence_inputs: tuple[str, ...] = ()
    parameter_group: str | None = None
    pad_inches: float = 0.02

    @property
    def display_name(self) -> str:
        prefix = "Supplement Figure" if self.selector == "S1" else "Figure"
        return f"{prefix} {self.selector}"


@dataclass(frozen=True)
class PlotContext:
    """Explicit input roots; an alternate data root never relocates evidence."""

    spec: FigureSpec
    params: Dict
    project_root: Path
    data_dir: Path
    evidence_dir: Path


@dataclass
class FigureResult:
    """A complete multi-panel figure plus the unchanged scientific diagnostics."""

    figure: plt.Figure
    diagnostics: dict[str, float | int]


# -----------------------------------------------------------------------------
# Scientific helpers (unchanged)
# -----------------------------------------------------------------------------
def ns_momenta(L: int) -> np.ndarray:
    """Positive Neveu--Schwarz momenta in (0, pi)."""
    n = np.arange(L // 2, dtype=float)
    return (2.0 * n + 1.0) * np.pi / float(L)

def theta_grads(h: float, gamma: float, k: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Return partial_h theta_k and partial_gamma theta_k."""
    X = h - np.cos(k)
    Y = gamma * np.sin(k)
    Lam2 = X * X + Y * Y
    dh = -gamma * np.sin(k) / Lam2
    dg = X * np.sin(k) / Lam2
    return dh, dg

def channel_weights(h: float, gamma: float, k: np.ndarray, yh: float, yg: float) -> np.ndarray:
    """Channel weights x_k(y)."""
    dh, dg = theta_grads(h, gamma, k)
    return 0.25 * (yh * dh + yg * dg) ** 2

def KF_from_weights(x: np.ndarray) -> Tuple[float, float, float]:
    P2 = float(np.sum(x))
    P4 = float(np.sum(x * x))
    return P4 / (P2 * P2), P2, P4

def KF_point(h: float, gamma: float, y: Tuple[float, float], L: int) -> float:
    k = ns_momenta(L)
    x = channel_weights(h, gamma, k, y[0], y[1])
    return KF_from_weights(x)[0]

def _odd_sequence(nmax: int) -> np.ndarray:
    return np.arange(1.0, 2.0 * nmax, 2.0, dtype=float)

def Phi(mu: np.ndarray | float, nmax: int = 50000) -> np.ndarray | float:
    """Ising scaling function Phi(mu), with Phi(0)=2/3."""
    kap = _odd_sequence(nmax)
    mu_arr = np.atleast_1d(np.asarray(mu, dtype=float))
    out = np.empty_like(mu_arr)
    for i, m in enumerate(mu_arr):
        d = kap * kap + m * m
        denom = np.sum((kap * kap) / (d * d))
        numer = np.sum((kap ** 4) / (d ** 4))
        out[i] = numer / (denom * denom)
    return out[0] if np.ndim(mu) == 0 else out

def Psi(w: np.ndarray | float, nmax: int = 50000) -> np.ndarray | float:
    """Lifshitz relevant-direction scaling function Psi(w)."""
    kap = _odd_sequence(nmax)
    w_arr = np.atleast_1d(np.asarray(w, dtype=float))
    out = np.empty_like(w_arr)
    for i, ww in enumerate(w_arr):
        d = kap * kap + 4.0 * ww * ww
        denom = np.sum((kap ** -2) / (d * d))
        numer = np.sum((kap ** -4) / (d ** 4))
        out[i] = numer / (denom * denom)
    return out[0] if np.ndim(w) == 0 else out

def KFcrit_p(p: np.ndarray | float) -> np.ndarray | float:
    """Critical envelope formula for x_k ~ k^{-p}."""
    p_arr = np.asarray(p, dtype=float)
    numer = (1.0 - 2.0 ** (-2.0 * p_arr)) * zeta(2.0 * p_arr)
    denom = ((1.0 - 2.0 ** (-p_arr)) * zeta(p_arr)) ** 2
    out = numer / denom
    return float(out) if np.ndim(p) == 0 else out

def theta_angle(h: float, gamma: float, k: np.ndarray) -> np.ndarray:
    """Bogoliubov angle theta_k = atan2(gamma sin k, h-cos k)."""
    return np.arctan2(gamma * np.sin(k), h - np.cos(k))

def weak_quench_probabilities_h(h0: float, gamma: float, delta: float, L: int) -> np.ndarray:
    """
    Exact one-sided quench probabilities for h -> h + delta at fixed gamma.

    For each independent mode,
        p_k = sin^2[(theta_f - theta_i)/2].
    """
    k = ns_momenta(L)
    th_i = theta_angle(h0, gamma, k)
    th_f = theta_angle(h0 + delta, gamma, k)
    dth = th_f - th_i
    return np.sin(0.5 * dth) ** 2

def R_from_probabilities(p: np.ndarray) -> Tuple[float, float, float]:
    """Return R=(<N>-Var(N))/<N>^2, <N>, Var(N) for Bernoulli-independent modes."""
    meanN = float(np.sum(p))
    varN = float(np.sum(p * (1.0 - p)))
    R = (meanN - varN) / (meanN * meanN)
    return R, meanN, varN

# -----------------------------------------------------------------------------
# Shared exporter and paths
# -----------------------------------------------------------------------------
def save_figure(fig: plt.Figure, spec: FigureSpec, outdir: Path) -> None:
    """Use the SAME spec that selected the renderer; never infer a legacy ID."""
    save_named_figure(fig, spec.output_stem, outdir, pad_inches=spec.pad_inches)


def save_named_figure(
    fig: plt.Figure, basename: str, outdir: Path, *, pad_inches: float = 0.02,
) -> None:
    """Stage and validate a standard-canvas PDF/PNG pair, then copy it out.

    ``pad_inches`` remains a compatibility argument for the frozen registry;
    standard-canvas export deliberately does not apply a tight bounding box.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    pdf_path = outdir / f"{basename}.pdf"
    png_path = outdir / f"{basename}.png"
    project_root = Path(__file__).resolve().parents[2]
    staging_root = project_root / "build" / "figure-staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{basename}-", dir=staging_root) as staging:
        temporary_pdf = Path(staging) / f"{basename}.pdf"
        temporary_png = Path(staging) / f"{basename}.png"
        fig.savefig(temporary_pdf)
        fig.savefig(temporary_png, dpi=300, facecolor="white")
        if temporary_pdf.stat().st_size == 0 or temporary_pdf.read_bytes()[:4] != b"%PDF":
            raise RuntimeError(f"invalid generated PDF: {temporary_pdf}")
        if temporary_png.stat().st_size == 0 or temporary_png.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError(f"invalid generated PNG: {temporary_png}")
        # Keep all intermediate paths outside the public figure directory.  A
        # direct copy is deliberate: on synchronized filesystems, replacing a
        # sibling temporary file can leave a delayed hidden copy in figures/.
        shutil.copyfile(temporary_pdf, pdf_path)
        shutil.copyfile(temporary_png, png_path)
    if pdf_path.read_bytes()[:4] != b"%PDF":
        raise RuntimeError(f"invalid written PDF: {pdf_path}")
    if png_path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"invalid written PNG: {png_path}")
    print(f"wrote {pdf_path}")
    print(f"wrote {png_path}")
    plt.close(fig)

def default_paths(
    outdir: Optional[str], data_dir: Optional[str] = None, *, allow_canonical_output: bool = False,
) -> Tuple[Path, Path]:
    project_root = Path(__file__).resolve().parents[2]
    if outdir is None:
        figures_dir = project_root / "build" / "regenerated_figures"
    else:
        figures_dir = Path(outdir).resolve()
    resolved_data = Path(data_dir).resolve() if data_dir else project_root / "data" / "reproducibility"
    if figures_dir.is_relative_to((project_root / "figures").resolve()) and not allow_canonical_output:
        raise ValueError(
            "refusing to overwrite frozen figures/; use build/regenerated_figures "
            "or pass --allow-canonical-output explicitly"
        )
    if not resolved_data.is_dir():
        raise FileNotFoundError(f"input data directory does not exist: {resolved_data}")
    return figures_dir, resolved_data

# -----------------------------------------------------------------------------
# Parameter presets: semantic groups, identical expressions and grids
# -----------------------------------------------------------------------------
def get_params(mode: str) -> Dict:
    if mode == "fast":
        return {
            "phi_nmax": 15000,
            "psi_nmax": 15000,
            "tfim_critical_concentration": {
                "Ls": np.array([16, 24, 32, 48, 64, 96, 128, 192, 256]),
            },
            "scaling_and_envelope": {
                "Ls": [256, 512, 1024],
                "mus": np.linspace(-6.0, 6.0, 41),
                "mu_grid": np.linspace(-6.0, 6.0, 301),
            },
            "lifshitz_anisotropy_scaling": {
                "fixed_L": 8192,
                "gammas": np.logspace(-5.0, -0.5, 24),
                "scaling_Ls": [2048, 8192],
                "w_data": np.array([0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 25.0, 45.0]),
                "w_curve": np.geomspace(0.05, 100.0, 240),
            },
            "xy_directional_profiles": {
                "L": 512,
                "point": (0.8, 0.5),
                "lifshitz_s": 0.05,
                "phi_grid": np.linspace(0.0, np.pi, 181),
            },
            "weak_quench_extraction": {
                "L": 128,
                "h0": 1.0,
                "gamma": 1.0,
                "deltas_panel": [0.0005, 0.0015, 0.003],
                "delta_grid": np.linspace(0.0002, 0.0035, 40),
                "n_show": 80,
            },
        }
    elif mode == "publication":
        return {
            "phi_nmax": 50000,
            "psi_nmax": 50000,
            "tfim_critical_concentration": {
                "Ls": np.array([16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024]),
            },
            "scaling_and_envelope": {
                "Ls": [512, 2048, 8192, 32768],
                "mus": np.linspace(-6.0, 6.0, 61),
                "mu_grid": np.linspace(-6.0, 6.0, 401),
            },
            "lifshitz_anisotropy_scaling": {
                "fixed_L": 2 ** 16,
                "gammas": np.logspace(-5.0, -0.5, 30),
                "scaling_Ls": [4096, 16384, 65536],
                "w_data": np.array([0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 25.0, 45.0]),
                "w_curve": np.geomspace(0.05, 100.0, 320),
            },
            "xy_directional_profiles": {
                "L": 2000,
                "point": (0.8, 0.5),
                "lifshitz_s": 0.05,
                "phi_grid": np.linspace(0.0, np.pi, 241),
            },
            "weak_quench_extraction": {
                "L": 256,
                "h0": 1.0,
                "gamma": 1.0,
                "deltas_panel": [0.0005, 0.0015, 0.003],
                "delta_grid": np.linspace(0.0002, 0.0035, 48),
                "n_show": 100,
            },
        }
    else:
        raise ValueError(f"Unknown mode: {mode}")

# -----------------------------------------------------------------------------
# Interacting-model readers and shared distribution helpers (Figures 4 and 5)
# -----------------------------------------------------------------------------
def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

def as_float(value: str) -> float:
    return float(str(value).strip()) if str(value).strip() else np.nan

def model_rows(rows: list[dict[str, str]], model: str) -> list[dict[str, str]]:
    selected = [row for row in rows if row.get("model", "") == model]
    selected.sort(key=lambda row: (as_float(row.get("lambda_or_g", "nan")), int(row["L"])))
    return selected

def potts_series(rows: list[dict[str, str]]) -> tuple[np.ndarray, np.ndarray]:
    selected = model_rows(rows, "Potts")
    selected.sort(key=lambda row: int(row["L"]))
    inv_l = np.array([1.0 / int(row["L"]) for row in selected], dtype=float)
    values = np.array([as_float(row["KF"]) for row in selected], dtype=float)
    return inv_l, values

def nnn_series_by_coupling(
    rows: list[dict[str, str]],
) -> dict[float, tuple[np.ndarray, np.ndarray]]:
    grouped: dict[float, list[dict[str, str]]] = defaultdict(list)
    for row in model_rows(rows, "NNN-TFIM"):
        grouped[as_float(row["lambda_or_g"])].append(row)
    series: dict[float, tuple[np.ndarray, np.ndarray]] = {}
    for coupling, selected in grouped.items():
        selected.sort(key=lambda row: int(row["L"]))
        inv_l = np.array([1.0 / int(row["L"]) for row in selected], dtype=float)
        values = np.array([as_float(row["KF"]) for row in selected], dtype=float)
        series[coupling] = (inv_l, values)
    return dict(sorted(series.items()))

def ideal_odd_ladder_weights(p: float, count: int, cutoff: int = 200_000) -> np.ndarray:
    indices = np.arange(cutoff, dtype=float)
    raw = (2.0 * indices + 1.0) ** (-p)
    raw /= raw.sum()
    return raw[:count]

def normalized_cft_level_weights(delta: float, count: int, total_weight: float) -> np.ndarray:
    """Return the first ``count`` normalized conformal-level response weights."""
    coefficients = np.empty(count, dtype=float)
    coefficients[0] = 1.0
    for n in range(count - 1):
        coefficients[n + 1] = coefficients[n] * ((delta + n) / (n + 1.0)) ** 2
    levels = np.arange(count, dtype=float)
    raw = coefficients / (delta + 2.0 * levels) ** 2
    return raw / total_weight

def _legacy_potts_display_row(row: dict[str, str]) -> bool:
    """Read the frozen display flag; 'fig7' is historical CSV provenance only."""
    return row["displayed_in_fig7"] == "True"


def _require_legacy_nnn_receipt(receipt: dict, display_name: str) -> None:
    """Preserve the sealed decision ID; do not renumber scientific provenance."""
    legacy_decision_id = "FIG7-ISING-DISTRIBUTION-CONVERGENCE-R1/OPTION-A"
    if receipt["decision_id"] != legacy_decision_id:
        raise ValueError(f"{display_name} NNN receipt has an unexpected decision identifier")


# -----------------------------------------------------------------------------
# Figure 1 | fig:twothirds
# -----------------------------------------------------------------------------
def plot_fig1_tfim_critical_concentration(context: PlotContext) -> FigureResult:
    """Figure 1 (fig:twothirds).

    (a) Total-response scaling; (b) single/double soft ladders;
    (c) exact finite-size concentration. Input: analytic TFIM/XX moments and
    the tfim_critical_concentration parameter group.
    Return the complete figure; the registry-controlled exporter owns saving.
    """
    configure_plotting()
    diagnostics: dict[str, float | int] = {}
    params = context.params
    Ls = params["tfim_critical_concentration"]["Ls"]
    Lsf = Ls.astype(float)

    # Exact finite-size moments from Eqs. (P2P4-exact) and (xx-moments).
    P2_tfim = Lsf * (Lsf - 1.0) / 32.0
    P2_xx = Lsf * (Lsf - 2.0) / 16.0
    KF_tfim = (2.0 / 3.0) * (Lsf * Lsf + Lsf - 3.0) / (Lsf * (Lsf - 1.0))
    KF_xx = (1.0 / 3.0) * (Lsf * Lsf + 2.0 * Lsf - 12.0) / (Lsf * (Lsf - 2.0))

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(510.0 / 72.27, 2.60))

    # PANEL (a) Total-response scaling
    ax1.loglog(Ls, P2_tfim, "o-", color=C["blue"], ms=3.4,
               mfc="white", mew=0.9, label=r"TFIM $\partial_h$")
    ax1.loglog(Ls, P2_xx, "s-", color=C["orange"], ms=3.2,
               mfc="white", mew=0.9, label=r"XX $\partial_\gamma$")
    ax1.loglog(Ls, Lsf * Lsf / 64.0, ":", color=C["gray"], lw=1.0,
               label=r"$\propto L^2$")
    ax1.set_xlabel(r"system size $L$")
    ax1.set_ylabel(r"total response $P_2$")
    ax1.margins(0.05)
    ax1.legend(loc="upper left", fontsize=8.0, handlelength=1.2)
    ax1.set_title(r"(a)", loc="left", fontweight="bold", pad=3.0)

    # PANEL (b) Single/double soft-ladder weights
    # Limiting normalized distributions: one TFIM ladder versus two equal XX
    # ladders.  Each XX side carries one half of the same within-ladder shape.
    nshow = 5
    nn = np.arange(nshow, dtype=float)
    pin = (8.0 / np.pi ** 2) / (2.0 * nn + 1.0) ** 2
    width = 0.24
    ax2.bar(nn - width, pin, width=width, color=C["blue"],
            edgecolor=C["black"], lw=0.5, label=r"TFIM ladder")
    ax2.bar(nn, 0.5 * pin, width=width, color=C["orange"],
            edgecolor=C["black"], lw=0.5, label=r"XX left")
    ax2.bar(nn + width, 0.5 * pin, width=width, color=C["sky"],
            edgecolor=C["black"], lw=0.5, label=r"XX right")
    ax2.set_xlabel(r"soft-ladder index $n$")
    ax2.set_ylabel(r"normalized weight")
    ax2.set_xticks(nn)
    ax2.set_ylim(0.0, 0.9)
    ax2.legend(loc="upper right", fontsize=8.0, handlelength=1.1,
               handletextpad=0.45, labelspacing=0.25)
    ax2.set_title(r"(b)", loc="left", fontweight="bold", pad=3.0)

    # PANEL (c) Exact finite-size concentration
    ax3.plot(1.0 / Lsf, KF_tfim, "o-", color=C["blue"], ms=3.4,
             mfc="white", mew=0.9, label=r"TFIM")
    ax3.plot(1.0 / Lsf, KF_xx, "s-", color=C["orange"], ms=3.2,
             mfc="white", mew=0.9, label=r"XX")
    ax3.axhline(2.0 / 3.0, color=C["blue"], ls="--", lw=0.9, zorder=0,
                label=r"$2/3$")
    ax3.axhline(1.0 / 3.0, color=C["orange"], ls="--", lw=0.9, zorder=0,
                label=r"$1/3$")
    ax3.set_xlabel(r"$1/L$")
    ax3.set_ylabel(r"concentration $K_F$")
    ax3.set_xlim(0.0, 1.05 / np.min(Lsf))
    ax3.set_ylim(0.30, 0.77)
    ax3.legend(loc="center right", fontsize=8.0)
    ax3.set_title(r"(c)", loc="left", fontweight="bold", pad=3.0)

    fig.subplots_adjust(left=0.085, right=0.99, bottom=0.19, top=0.91, wspace=0.43)

    diagnostics["K_F(h_c,L_max)"] = float(KF_tfim[-1])
    diagnostics["K_F^XX(0,L_max)"] = float(KF_xx[-1])
    diagnostics[f"{context.spec.display_name} max L"] = int(Ls[-1])
    diagnostics["pi_0"] = float(pin[0])
    return FigureResult(fig, diagnostics)


# -----------------------------------------------------------------------------
# Figure 2 | fig:collapse
# -----------------------------------------------------------------------------
def plot_fig2_scaling_and_envelope(context: PlotContext) -> FigureResult:
    """Figure 2 (fig:collapse).

    (a) TFIM scaling collapse; (b) odd-ladder envelope versus exponent.
    Inputs: scaling_and_envelope parameters; Phi and KFcrit_p.
    Return the complete figure; the registry-controlled exporter owns saving.
    """
    configure_plotting()
    diagnostics: dict[str, float | int] = {}
    params = context.params
    mu_curve = params["scaling_and_envelope"]["mu_grid"]
    mus_data = params["scaling_and_envelope"]["mus"]
    Llist = params["scaling_and_envelope"]["Ls"]

    phicurve = Phi(mu_curve, nmax=params["phi_nmax"])
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(WIDE, 2.6))

    # PANEL (a) TFIM scaling collapse
    ax1.plot(mu_curve, phicurve, color=C["black"], lw=1.4, label=r"$\Phi(\mu)$")
    ax1.axhline(2.0 / 3.0, color=C["red"], ls=":", lw=1.0, label=r"$2/3$")
    palette = [C["orange"], C["green"], C["blue"], C["purple"]]
    markers = ['o', 's', '^', 'D']
    for L, col, marker in zip(Llist, palette, markers):
        k = ns_momenta(int(L))
        vals = []
        for mu in mus_data:
            h = 1.0 + mu * np.pi / float(L)
            vals.append(KF_from_weights(channel_weights(h, 1.0, k, 1.0, 0.0))[0])
        ax1.plot(mus_data, vals, marker, color=col, ms=3.1, mfc="white", mew=0.9, label=rf"$L={L}$")
    ax1.set_xlabel(r"$\mu=(h-1)L/\pi$")
    ax1.set_ylabel(r"$K_F(h,L)$")
    ax1.set_ylim(0.02, 0.82)
    leg = ax1.legend(loc="center left", fontsize=8.0, handlelength=1.0, handletextpad=0.5,
                     borderpad=0.25, labelspacing=0.25, frameon=True, framealpha=0.85,
                     facecolor="white", edgecolor="white")
    for handle in leg.legend_handles:
        try:
            handle.set_markerfacecolor("white")
        except Exception:
            pass
    ax1.text(0.0, 2.0 / 3.0 + 0.05, r"$\Phi(0)=2/3$", fontsize=8)
    ax1.text(0.04, 0.90, r"(a)", transform=ax1.transAxes, fontweight="bold")

    # PANEL (b) Odd-ladder envelope
    pgrid = np.linspace(1.02, 6.0, 320)
    ax2.plot(pgrid, KFcrit_p(pgrid), color=C["blue"], lw=1.5)
    ax2.axhline(2.0 / 3.0, color=C["red"], ls="--", lw=1.0, label=r"$2/3$")
    ax2.plot([2.0], [2.0 / 3.0], "o", color=C["red"], ms=5)
    ax2.set_xlabel(r"envelope exponent $p$  ($x_k\sim k^{-p}$)")
    ax2.set_ylabel(r"$K_F^{\mathrm{env}}(p)$")
    ax2.set_xlim(1.0, 6.0)
    ax2.set_ylim(-0.02, 1.06)
    ax2.annotate(
        r"TFIM: $p=2$",
        xy=(2.0, 0.65),
        xytext=(2.5, 0.50),
        arrowprops=dict(arrowstyle="->", color="black", shrinkB=6.0),
        fontsize=8.0,
    )
    ax2.text(4.45, 0.90, r"large $p$: $K_F\to1$", color="0.35", fontsize=8.0)
    ax2.text(1.35, 0.08, r"$p\to1^+$: $K_F\to0$", color="0.35", fontsize=8.0)
    ax2.text(0.04, 0.90, r"(b)", transform=ax2.transAxes, fontweight="bold")
    ax2.legend(loc="lower right", fontsize=8)

    fig.subplots_adjust(left=0.10, right=0.99, bottom=0.22, top=0.96, wspace=0.28)

    diagnostics["Phi(0)"] = float(Phi(0.0, nmax=params["phi_nmax"]))
    diagnostics["KFcrit_p(2)"] = float(KFcrit_p(2.0))
    return FigureResult(fig, diagnostics)


# -----------------------------------------------------------------------------
# Figure 3 | fig:lifshitz
# -----------------------------------------------------------------------------
def plot_fig3_lifshitz_anisotropy_scaling(context: PlotContext) -> FigureResult:
    """Figure 3 (fig:lifshitz).

    (a) Two tangent directions at fixed large L; (b) Lifshitz scaling
    functions. Inputs: lifshitz_anisotropy_scaling parameters; Phi/Psi and
    exact free-fermion channel sums.
    Return the complete figure; the registry-controlled exporter owns saving.
    """
    configure_plotting()
    diagnostics: dict[str, float | int] = {}
    params = context.params
    Lfixed = params["lifshitz_anisotropy_scaling"]["fixed_L"]
    gammas = params["lifshitz_anisotropy_scaling"]["gammas"]
    w_curve = params["lifshitz_anisotropy_scaling"]["w_curve"]
    w_data = params["lifshitz_anisotropy_scaling"]["w_data"]
    scaling_Ls = params["lifshitz_anisotropy_scaling"]["scaling_Ls"]

    KFh = np.array([KF_point(1.0, float(g), (1.0, 0.0), Lfixed) for g in gammas])
    KFg = np.array([KF_point(1.0, float(g), (0.0, 1.0), Lfixed) for g in gammas])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(WIDE, 2.7))

    # PANEL (a) Tangent-direction comparison
    ax1.semilogx(gammas, KFh, "o-", color=C["blue"], ms=3.8, mfc="white", mew=0.9,
                 label=r"$y=\partial_h$")
    ax1.semilogx(gammas, KFg, "s-", color=C["green"], ms=3.8, mfc="white", mew=0.9,
                 label=r"$y=\partial_\gamma$")
    ax1.axhline(2.0 / 3.0, color=C["red"], ls="--", lw=0.9, label=r"$2/3$")
    ax1.set_xlabel(r"anisotropy $\gamma$ at $h=1$")
    ax1.set_ylabel(r"$K_F(1,\gamma;L)$")
    ax1.set_ylim(-0.03, 1.03)
    ax1.legend(loc="best")
    ax1.text(0.04, 0.90, r"(a)", transform=ax1.transAxes, fontweight="bold")

    # PANEL (b) Lifshitz scaling functions
    ax2.plot(w_curve, Phi(2.0 * w_curve, nmax=params["phi_nmax"]), color=C["green"], lw=1.35,
             label=r"$K_F^{(\gamma)}(w)=\Phi(2w)$")
    ax2.plot(w_curve, Psi(w_curve, nmax=params["psi_nmax"]), color=C["blue"], lw=1.35,
             label=r"$K_F^{(h)}(w)=\Psi(w)$")
    ax2.axhline(2.0 / 3.0, color=C["red"], ls="--", lw=0.9, label=r"$2/3$")
    marker_sets = ["o", "s", "^"]
    color_sets = [C["orange"], C["purple"], C["sky"]]
    for L, mk, col in zip(scaling_Ls, marker_sets, color_sets):
        ws = []
        vals_h = []
        vals_g = []
        for w in w_data:
            gamma = w * np.pi / float(L)
            if gamma > 0.05:   # stay inside the Lifshitz scaling window
                continue
            ws.append(w)
            vals_h.append(KF_point(1.0, gamma, (1.0, 0.0), int(L)))
            vals_g.append(KF_point(1.0, gamma, (0.0, 1.0), int(L)))
        ax2.plot(ws, vals_h, mk, color=col, ms=3.4, mfc="white", mew=0.9)
        ax2.plot(ws, vals_g, mk, color=col, ms=3.4, mfc=col, mew=0.5, label=rf"data $L={L}$")
    ax2.set_xscale("log")
    ax2.set_xlabel(r"$w=\gamma L/\pi$")
    ax2.set_ylabel(r"$K_F(w)$")
    ax2.set_xlim(float(np.min(w_curve)), float(np.max(w_curve)))
    ax2.set_ylim(0.0, 1.03)
    ax2.legend(loc="right", bbox_to_anchor=(1.0, 0.35), fontsize=6.6, ncol=1)
    ax2.text(0.04, 0.90, r"(b)", transform=ax2.transAxes, fontweight="bold")

    fig.subplots_adjust(bottom=0.16, wspace=0.30)

    diagnostics["Psi(0)"] = float(Psi(0.0, nmax=params["psi_nmax"]))
    diagnostics[f"{context.spec.display_name} fixed-L K_h(gamma_min)"] = float(KFh[0])
    diagnostics[f"{context.spec.display_name} fixed-L K_g(gamma_min)"] = float(KFg[0])
    return FigureResult(fig, diagnostics)


# -----------------------------------------------------------------------------
# Figure 4 | fig:interacting-benchmarks
# -----------------------------------------------------------------------------
def plot_fig4_interacting_benchmarks(context: PlotContext) -> FigureResult:
    """Figure 4 (fig:interacting-benchmarks).

    (a) Potts finite-size values and fixed references; (b) NNN-TFIM
    and exact TFIM sequences. Inputs: interacting_benchmarks.csv,
    potts_outcome_aware_fss.csv, potts_theory_guided_7over5_receipt.json,
    envelope_predictions_table.csv. Existing fit coefficients are READ,
    not refitted. All diagnostics are retained.
    Return the complete figure; the registry-controlled exporter owns saving.
    """
    configure_plotting()
    diagnostics: dict[str, float | int] = {}
    data_dir = context.data_dir
    rows = read_csv(data_dir / "interacting_benchmarks.csv")
    potts_rows = read_csv(data_dir / "potts_outcome_aware_fss.csv")
    with (data_dir / "potts_theory_guided_7over5_receipt.json").open(encoding="utf-8") as handle:
        potts_fit_receipt = json.load(handle)
    figure, axes = plt.subplots(
        1, 2, figsize=(510.0 / 72.27, 3.0), sharey=False,
        constrained_layout=True,
    )

    # PANEL (a) Potts finite-size comparison
    ax = axes[0]
    primary_rows = [row for row in potts_rows if row["primary_fit"] == "True"]
    primary_rows.sort(key=lambda row: int(row["L"]))
    correction_power = float(
        potts_fit_receipt["theory_contract"]["relative_analytic_background_correction"]
    )
    scaled_l = np.array([int(row["L"]) ** (-correction_power) for row in primary_rows])
    values = np.array([as_float(row["midpoint"]) for row in primary_rows])
    ax.plot(
        scaled_l, values, marker="o", linestyle="None", color=C["blue"],
        markerfacecolor="white", markeredgewidth=1.1, ms=4.6, zorder=3,
    )
    primary_fit = potts_fit_receipt["primary_KF_contract"]["fit"]
    intercept = float(primary_fit["intercept"])
    slope = float(primary_fit["amplitudes"][0])
    cft_target = float(potts_fit_receipt["cft_target"])
    ax.axhline(cft_target, color=C["orange"], linestyle="-.", linewidth=1.0,
               zorder=0)
    envelope_rows = read_csv(data_dir / "envelope_predictions_table.csv")
    ideal_row = next(row for row in envelope_rows
                     if row["label"] == "3-state Potts energy")
    ideal_target = as_float(ideal_row["KF_env"])
    ax.axhline(ideal_target, color=C["purple"], linestyle=":", linewidth=1.2,
               zorder=0)
    ax.text(0.04, 0.93, r"(a)", transform=ax.transAxes, fontsize=10, va="top")
    relative = float(primary_fit["signed_relative_deviation_percent"])
    ax.text(
        0.025, cft_target + 0.0022, r"descendant-resolved CFT",
        color=C["orange"], fontsize=8.0, ha="left", va="bottom",
    )
    ax.text(
        0.025, ideal_target + 0.0022, r"exponent-only odd ladder",
        color=C["purple"], fontsize=8.0, ha="left", va="bottom",
    )
    ax.set_xlabel(r"$L^{-7/5}$")
    ax.set_ylabel(r"$K_F$")
    ax.set_xlim(0.0, 0.086)
    ax.set_ylim(0.79, 0.925)
    ax.set_xticks([0.0, 0.02, 0.04, 0.06, 0.08])

    # PANEL (b) NNN-TFIM and exact TFIM
    ax = axes[1]
    nnn_series = nnn_series_by_coupling(rows)

    # The exact NS-sector TFIM sequence and its thermodynamic endpoint are
    # known in closed form.  Extend that benchmark to the large sizes used in
    # Fig. 1; sparse markers identify actual even-L sequence values, while the
    # solid line joins them to the exact L -> infinity endpoint.
    exact_sizes = np.array(
        [6, 8, 10, 12, 14, 16, 18, 20, 24, 32, 48, 64, 96,
         128, 192, 256, 384, 512, 768, 1024],
        dtype=float,
    )
    exact_values = (
        FREE_ISING
        * (exact_sizes * exact_sizes + exact_sizes - 3.0)
        / (exact_sizes * (exact_sizes - 1.0))
    )
    exact_x = np.concatenate(([0.0], 1.0 / exact_sizes[::-1]))
    exact_y = np.concatenate(([FREE_ISING], exact_values[::-1]))
    ax.plot(
        exact_x, exact_y, color=C["black"], linestyle="-", linewidth=1.1,
        label=r"exact TFIM", zorder=2,
    )
    marker_mask = exact_sizes <= 512
    ax.plot(
        1.0 / exact_sizes[marker_mask], exact_values[marker_mask],
        marker="o", linestyle="None", color=C["black"],
        markerfacecolor="white", markeredgewidth=1.0, ms=3.8, zorder=3,
    )

    interacting_styles = [
        (C["green"], "s"),
        (C["purple"], "D"),
        (C["red"], "^"),
    ]
    interacting_series = [
        item for item in nnn_series.items() if item[0] > 0.0
    ]
    for (coupling, (x_values, y_values)), (color, marker) in zip(
        interacting_series, interacting_styles
    ):
        ax.plot(
            x_values, y_values, marker=marker, linestyle="None", color=color,
            markerfacecolor="white", markeredgewidth=1.0, ms=4.2,
            label=rf"$J_2={coupling:g}$", zorder=3,
        )
    ax.axhline(FREE_ISING, color=C["gray"], linestyle="--", linewidth=0.9,
               label=r"TFIM limit $2/3$", zorder=0)
    ax.text(0.04, 0.93, r"(b)", transform=ax.transAxes, fontsize=10,
            ha="left", va="top")
    ax.set_xlabel(r"$1/L$")
    ax.set_ylabel(r"$K_F$")
    ax.set_xlim(0.0, 0.175)
    ax.set_ylim(0.65, 0.915)
    ax.set_xticks([0.0, 0.05, 0.10, 0.15])
    ax.legend(
        loc="lower right", bbox_to_anchor=(0.98, 0.13), fontsize=8.0,
        frameon=False, handlelength=1.8, borderaxespad=0.0,
        labelspacing=0.25,
    )

    diagnostics[f"{context.spec.display_name} Potts 7/5-guide intercept"] = intercept
    diagnostics[f"{context.spec.display_name} Potts 7/5-guide amplitude"] = slope
    diagnostics[f"{context.spec.display_name} Potts 7/5 signed relative deviation percent"] = relative
    diagnostics[f"{context.spec.display_name} Potts CFT target"] = cft_target
    diagnostics[f"{context.spec.display_name} Potts ideal odd-ladder comparator"] = ideal_target
    exact_l20 = FREE_ISING * (20.0 * 20.0 + 20.0 - 3.0) / (20.0 * 19.0)
    l6_values = np.array([
        values[np.argmin(np.abs(x_values - 1.0 / 6.0))]
        for _, (x_values, values) in interacting_series
    ])
    l20_values = np.array([
        values[np.argmin(np.abs(x_values - 1.0 / 20.0))]
        for _, (x_values, values) in interacting_series
    ])
    diagnostics[f"{context.spec.display_name} NNN interacting spread contraction factor L6/L20"] = (
        float(np.ptp(l6_values) / np.ptp(l20_values))
    )
    diagnostics[f"{context.spec.display_name} NNN max abs deviation from exact TFIM at L20"] = (
        float(np.max(np.abs(l20_values - exact_l20)))
    )
    return FigureResult(figure, diagnostics)


# -----------------------------------------------------------------------------
# Figure 5 | fig:potts-weight-comparators
# -----------------------------------------------------------------------------
def plot_fig5_distribution_comparisons(context: PlotContext) -> FigureResult:
    """Figure 5 (fig:potts-weight-comparators).

    (a) Certified Potts ranks 1--15 and comparators, with a ranks 2--15
    inset; (b) NNN-TFIM distributions and exact L=20 TFIM, with ranks 2--10
    inset. Inputs: potts_L14_certified_ranked_weights.csv,
    nnn_ranked_distribution_convergence.csv and its receipt, plus
    evidence_dir/cft/cft_kf_results.json. Historical flags/receipt IDs
    are read through explicit legacy adapters, never renumbered.
    Return the complete figure; the registry-controlled exporter owns saving.
    """
    configure_plotting()
    diagnostics: dict[str, float | int] = {}
    data_dir = context.data_dir
    rows = read_csv(data_dir / "potts_L14_certified_ranked_weights.csv")
    selected = [row for row in rows if _legacy_potts_display_row(row)]
    selected.sort(key=lambda row: int(row["channel_rank"]))
    count = len(selected)
    if count != 15 or [int(row["channel_rank"]) for row in selected] != list(range(1, 16)):
        raise ValueError(f"{context.spec.display_name} requires exactly the certified ranks 1--15")
    if any(as_float(row["weight_lower"]) <= 0.0 for row in selected):
        raise ValueError(f"zero-inclusive cluster entered the {context.spec.display_name} display set")
    ranks = np.array([int(row["channel_rank"]) for row in selected], dtype=int)
    potts_weights = np.array([as_float(row["weight_central"]) for row in selected], dtype=float)
    ideal_weights = ideal_odd_ladder_weights(p=12.0 / 5.0, count=count)
    cft_result_path = context.evidence_dir / "cft" / "cft_kf_results.json"
    with cft_result_path.open(encoding="utf-8") as handle:
        cft_result = json.load(handle)
    cft_total_weight = float(cft_result["delta_4_over_5"]["S1"])
    cft_weights = normalized_cft_level_weights(
        delta=4.0 / 5.0, count=count, total_weight=cft_total_weight,
    )

    convergence_rows = read_csv(data_dir / "nnn_ranked_distribution_convergence.csv")
    receipt_path = data_dir / "nnn_ranked_distribution_convergence_receipt.json"
    with receipt_path.open(encoding="utf-8") as handle:
        convergence_receipt = json.load(handle)
    _require_legacy_nnn_receipt(convergence_receipt, context.spec.display_name)

    figure, axes = plt.subplots(
        1, 2, figsize=(510.0 / 72.27, 2.60), constrained_layout=True,
    )
    ax_potts, ax_ising = axes

    # PANEL (a) Potts ranked weights
    # Keep the Potts color grammar identical to Figure 4(a): lattice data blue,
    # CFT orange, and the exponent-only ideal comparator purple.
    potts_series = (
        (potts_weights, C["blue"], r"certified Potts ranks, $L=14$"),
        (cft_weights, C["orange"], r"CFT levels, $\Delta=4/5$"),
        (ideal_weights, C["purple"], r"ideal odd ladder, $p=12/5$"),
    )
    potts_width = 0.25
    potts_offsets = (-potts_width, 0.0, potts_width)
    for (weights, color, label), offset in zip(potts_series, potts_offsets):
        ax_potts.bar(
            ranks + offset, weights, width=potts_width,
            facecolor=color, edgecolor=C["black"], linewidth=0.45,
            label=label, zorder=3,
        )
    ax_potts.set_title(r"(a)", loc="left", fontsize=10, pad=2)
    ax_potts.set_xlabel(r"ranked channel $r$")
    ax_potts.set_xlim(0.5, 15.5)
    ax_potts.set_ylim(-0.015, 1.0)
    ax_potts.set_xticks([1, 3, 5, 7, 9, 11, 13, 15])
    ax_potts.legend(fontsize=8.0, frameon=False, loc="upper right")

    # PANEL (a) inset: Potts ranks 2--15
    potts_inset = ax_potts.inset_axes([0.39, 0.22, 0.58, 0.38])
    for (weights, color, _), offset in zip(potts_series, potts_offsets):
        potts_inset.bar(
            ranks[1:] + offset, weights[1:], width=potts_width,
            facecolor=color, edgecolor=C["black"], linewidth=0.4, zorder=3,
        )
    potts_inset.set_xlim(1.5, 15.5)
    potts_inset.set_ylim(0.0, 0.07)
    potts_inset.set_xticks([2, 5, 8, 11, 14])
    potts_inset.set_yticks([0.00, 0.02, 0.04, 0.06])
    potts_inset.set_title("linear zoom: ranks 2-15", fontsize=8.0, pad=1.5)
    potts_inset.tick_params(labelsize=8.0)

    # PANEL (b) NNN-TFIM distributions and exact TFIM
    def select_distribution(model: str, j2: float, size: int) -> List[dict]:
        selected_rows = [
            row for row in convergence_rows
            if row["model"] == model
            and abs(as_float(row["J2"]) - j2) < 1.0e-12
            and int(row["L"]) == size
        ]
        selected_rows.sort(key=lambda row: int(row["rank"]))
        return selected_rows

    displayed_ranks = np.arange(1, 11, dtype=int)
    exact_rows = select_distribution("exact-TFIM", 0.0, 20)
    exact_ranks = np.array([int(row["rank"]) for row in exact_rows], dtype=int)
    exact_weights = np.array([as_float(row["pi"]) for row in exact_rows], dtype=float)
    if not np.array_equal(exact_ranks, displayed_ranks):
        raise ValueError(f"{context.spec.display_name}(b) requires the ten exact L=20 NS channels")

    # The largest interaction supplies the most discriminating finite-size
    # distributional comparison.  Size is encoded by a monotone-luminance
    # cividis sequence, while
    # the exact finite-size lattice reference remains black.
    histogram_sizes = (6, 10, 14, 20)
    histogram_offsets = (-0.27, -0.09, 0.09, 0.27)
    histogram_width = 0.18
    size_colors = {
        size: plt.get_cmap("cividis")(fraction)
        for size, fraction in zip(histogram_sizes, (0.15, 0.38, 0.62, 0.85))
    }
    histogram_weights: Dict[int, np.ndarray] = {}
    for size, offset in zip(histogram_sizes, histogram_offsets):
        nnn_rows = select_distribution("NNN-TFIM", 0.20, size)
        weight_by_rank = {
            int(row["rank"]): as_float(row["pi"]) for row in nnn_rows
        }
        weights = np.array(
            [weight_by_rank.get(int(rank), 0.0) for rank in displayed_ranks],
            dtype=float,
        )
        histogram_weights[size] = weights
        ax_ising.bar(
            displayed_ranks + offset, weights, width=histogram_width,
            facecolor=size_colors[size], edgecolor=size_colors[size],
            linewidth=0.8, label=rf"$L={size}$", zorder=3,
        )

    ax_ising.plot(
        exact_ranks, exact_weights, color="black", linewidth=1.25,
        marker="o", markersize=3.3, markerfacecolor="white", markeredgewidth=0.8,
        label=r"exact TFIM, $L=20$", zorder=5,
    )

    ax_ising.set_title(r"(b)", loc="left", fontsize=10, pad=2)
    ax_ising.set_xlabel(r"ranked channel $r$")
    ax_ising.set_xlim(0.45, 10.55)
    ax_ising.set_ylim(-0.015, 1.0)
    ax_ising.set_xticks([1, 3, 5, 7, 9])
    legend_handles, legend_labels = ax_ising.get_legend_handles_labels()
    handle_by_label = dict(zip(legend_labels, legend_handles))
    desired_labels = [
        r"exact TFIM, $L=20$", r"$L=6$", r"$L=10$", r"$L=14$", r"$L=20$",
    ]
    ax_ising.legend(
        [handle_by_label[label] for label in desired_labels], desired_labels,
        fontsize=8.0, frameon=False, loc="upper right",
    )

    # PANEL (b) inset: ranks 2--10
    ising_inset = ax_ising.inset_axes([0.42, 0.20, 0.55, 0.34])
    for size, offset in zip(histogram_sizes, histogram_offsets):
        ising_inset.bar(
            displayed_ranks[1:] + offset, histogram_weights[size][1:],
            width=histogram_width, facecolor=size_colors[size],
            edgecolor=size_colors[size], linewidth=0.7, zorder=3,
        )
    ising_inset.plot(
        exact_ranks[1:], exact_weights[1:], color="black", linewidth=1.0,
        marker="o", markersize=3.1, markerfacecolor="white", markeredgewidth=0.7,
        zorder=5,
    )
    ising_inset.set_xlim(1.5, 10.5)
    ising_inset.set_ylim(-0.002, 0.11)
    ising_inset.set_xticks([2, 4, 6, 8, 10])
    ising_inset.set_yticks([0.00, 0.05, 0.10])
    ising_inset.set_title("linear zoom: ranks 2-10", fontsize=8.0, pad=1.5)
    ising_inset.tick_params(labelsize=8.0)
    figure.supylabel(r"normalized weight $\pi_r$", fontsize=9.0)

    for size in histogram_sizes:
        diagnostics[f"{context.spec.display_name} NNN J2=0.20 L={size} leading weight"] = float(
            histogram_weights[size][0]
        )
        diagnostics[f"{context.spec.display_name} NNN J2=0.20 L={size} displayed mass"] = float(
            histogram_weights[size].sum()
        )
    diagnostics[f"{context.spec.display_name} exact TFIM L=20 leading weight"] = float(exact_weights[0])

    diagnostics[f"{context.spec.display_name} Potts size"] = 14.0
    diagnostics[f"{context.spec.display_name} displayed rank count"] = float(count)
    diagnostics[f"{context.spec.display_name} Potts leading weight"] = float(potts_weights[0])
    diagnostics[f"{context.spec.display_name} Potts displayed mass"] = float(potts_weights.sum())
    diagnostics[f"{context.spec.display_name} Potts rank2-over-rank1"] = float(
        potts_weights[1] / potts_weights[0]
    )
    diagnostics[f"{context.spec.display_name} N_eig requested"] = float(selected[0]["n_eigenpairs_requested"])
    diagnostics[f"{context.spec.display_name} N_eig effective"] = float(selected[0]["n_eigenpairs_effective"])
    diagnostics[f"{context.spec.display_name} grouped channel count"] = float(selected[0]["n_grouped_channels"])
    diagnostics[f"{context.spec.display_name} CFT first-weight sum"] = float(cft_weights.sum())
    diagnostics[f"{context.spec.display_name} CFT rank2-over-rank1"] = float(cft_weights[1] / cft_weights[0])
    return FigureResult(figure, diagnostics)


# -----------------------------------------------------------------------------
# Figure 6 | fig:xy-directional-profiles
# -----------------------------------------------------------------------------
def plot_fig6_xy_directional_profiles(context: PlotContext) -> FigureResult:
    """Figure 6 (fig:xy-directional-profiles).

    (a) Gapped XY polar profile; (b) regulated near-Lifshitz profile.
    Located in the manuscript appendix. Inputs: xy_directional_profiles
    parameters and free-fermion sums; no interacting data files.
    Return the complete figure; the registry-controlled exporter owns saving.
    """
    configure_plotting()
    diagnostics: dict[str, float | int] = {}
    params = context.params
    h0, g0 = params["xy_directional_profiles"]["point"]
    L = params["xy_directional_profiles"]["L"]
    phi_grid = params["xy_directional_profiles"]["phi_grid"]
    lif_s = float(params["xy_directional_profiles"].get("lifshitz_s", 0.05))
    h_lif, g_lif = 1.0 + lif_s, lif_s
    k = ns_momenta(L)

    def polar_profile(hh: float, gg: float) -> Dict[str, object]:
        values = np.array([
            KF_from_weights(
                channel_weights(hh, gg, k, math.cos(phi), math.sin(phi))
            )[0]
            for phi in phi_grid
        ])
        maximum = float(np.max(values))
        minimum = float(np.min(values))
        normalized = values / maximum
        imax = int(np.argmax(normalized))
        imin = int(np.argmin(normalized))
        phi_max = float(phi_grid[imax])
        phi_min = float(phi_grid[imin])

        theta_half = np.asarray(phi_grid, dtype=float)
        radius_half = np.asarray(normalized, dtype=float)
        if len(theta_half) > 1 and np.isclose(theta_half[-1] - theta_half[0], np.pi):
            theta_half = theta_half[:-1]
            radius_half = radius_half[:-1]
        theta_full = np.concatenate([theta_half, theta_half + np.pi])
        radius_full = np.concatenate([radius_half, radius_half])
        theta_full = np.concatenate([theta_full, theta_full[:1]])
        radius_full = np.concatenate([radius_full, radius_full[:1]])

        return {
            "normalized": normalized,
            "theta_full": theta_full,
            "radius_full": radius_full,
            "ratio": maximum / minimum,
            "imax": imax,
            "imin": imin,
            "phi_max": phi_max,
            "phi_min": phi_min,
        }

    # PANEL (a) Gapped point; (b) regulated near-Lifshitz point
    generic = polar_profile(h0, g0)
    near_lifshitz = polar_profile(h_lif, g_lif)

    figure = plt.figure(figsize=(WIDE, 3.25))
    grid = figure.add_gridspec(1, 2, wspace=0.32)
    axes = [
        figure.add_subplot(grid[0, 0], projection="polar"),
        figure.add_subplot(grid[0, 1], projection="polar"),
    ]

    def draw_profile(ax, profile: Dict[str, object], tag: str, title: str) -> None:
        theta_full = np.asarray(profile["theta_full"], dtype=float)
        radius_full = np.asarray(profile["radius_full"], dtype=float)
        normalized = np.asarray(profile["normalized"], dtype=float)
        imax = int(profile["imax"])
        imin = int(profile["imin"])
        phi_max = float(profile["phi_max"])
        phi_min = float(profile["phi_min"])
        ax.plot(theta_full, radius_full, color=C["blue"], lw=1.7)
        for theta_mark in (phi_max, phi_max + np.pi):
            ax.plot(theta_mark, normalized[imax], "o", color=C["red"], ms=4.8, zorder=5)
        for theta_mark in (phi_min, phi_min + np.pi):
            ax.plot(theta_mark, normalized[imin], "s", color=C["purple"], ms=4.5,
                    mfc="white", mew=1.0, zorder=5)
        ax.set_theta_zero_location("E")
        ax.set_theta_direction(1)
        ax.set_thetagrids(
            [0, 45, 90, 135, 180, 225, 270, 315],
            labels=[r"$0$", r"$\pi/4$", r"$\pi/2$", r"$3\pi/4$", r"$\pi$",
                    r"$5\pi/4$", r"$3\pi/2$", r"$7\pi/4$"],
            fontsize=7.0,
        )
        ax.set_rlim(0.0, 1.08)
        ax.set_rticks([0.25, 0.50, 0.75, 1.00])
        ax.set_yticklabels([r"$0.25$", r"$0.50$", r"$0.75$", r"$1$"], fontsize=6.8)
        ax.grid(True, lw=0.55, alpha=0.65)
        ax.text(1.01, 0.50, r"$\hat{h}$", transform=ax.transAxes, fontsize=7.5,
                ha="left", va="center", color="0.25")
        ax.text(0.50, 1.0, r"$\hat{\gamma}$", transform=ax.transAxes, fontsize=7.5,
                ha="center", va="bottom", color="0.25")
        ax.text(0.00, 0.95, tag, transform=ax.transAxes, fontweight="bold")
        ax.text(
            0.58, 0.15,
            title + "\n" + rf"$K_F^{{\max}}/K_F^{{\min}}={float(profile['ratio']):.2f}$",
            transform=ax.transAxes,
            fontsize=7.0,
            va="bottom",
            bbox=dict(boxstyle="round,pad=0.24", facecolor="white",
                      edgecolor="0.82", alpha=0.90),
        )

    draw_profile(
        axes[0], generic, r"(a)",
        rf"generic $(h,\gamma)=({h0:.1f},{g0:.1f})$",
    )
    draw_profile(
        axes[1], near_lifshitz, r"(b)",
        rf"near Lifshitz $(1+s,s)$, $s={lif_s:.2f}$",
    )
    figure.subplots_adjust(wspace=0.32)

    diagnostics[f"{context.spec.display_name} K_F max/min"] = float(generic["ratio"])
    diagnostics[f"{context.spec.display_name} phi_max/pi"] = float(generic["phi_max"]) / np.pi
    diagnostics[f"{context.spec.display_name} phi_min/pi"] = float(generic["phi_min"]) / np.pi
    diagnostics[f"{context.spec.display_name} near-Lifshitz s"] = lif_s
    diagnostics[f"{context.spec.display_name} near-Lifshitz K_F max/min"] = float(near_lifshitz["ratio"])
    return FigureResult(figure, diagnostics)


# -----------------------------------------------------------------------------
# Figure S1 | fig:quench
# -----------------------------------------------------------------------------
def plot_figS1_weak_quench_extraction(context: PlotContext) -> FigureResult:
    """Figure S1 (fig:quench).

    (a) Normalized excitation weights; (b) counting ratio versus quench
    amplitude. Inputs: weak_quench_extraction parameters and exact BdG
    pair probabilities. CLI/combined Figure S1; standalone Supplement
    Figure 1. No external data files.
    Return the complete figure; the registry-controlled exporter owns saving.
    """
    configure_plotting()
    diagnostics: dict[str, float | int] = {}
    params = context.params
    L = params["weak_quench_extraction"]["L"]
    h0 = params["weak_quench_extraction"]["h0"]
    gamma = params["weak_quench_extraction"]["gamma"]
    deltas_panel = params["weak_quench_extraction"]["deltas_panel"]
    delta_grid = params["weak_quench_extraction"]["delta_grid"]
    n_show = params["weak_quench_extraction"]["n_show"]

    k = ns_momenta(L)
    x = channel_weights(h0, gamma, k, 1.0, 0.0)
    K_exact, _, _ = KF_from_weights(x)
    pi_quad = x / np.sum(x)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(WIDE, 2.75))

    # PANEL (a) Excitation weights
    nind = np.arange(1, min(n_show, len(k)) + 1)
    ax1.loglog(nind, pi_quad[:len(nind)], "--", color=C["black"], lw=1.2,
               label=r"quadratic prediction $x_k/P_2$")
    panel_cols = [C["blue"], C["orange"], C["purple"]]
    panel_markers = ["o", "s", "^"]

    for i, (delta, col, mk) in enumerate(zip(deltas_panel, panel_cols, panel_markers)):
        p = weak_quench_probabilities_h(h0, gamma, float(delta), L)
        pi_p = p / np.sum(p)

        # Sparse markers with different shapes, shifted by curve index.
        ax1.loglog(
            nind,
            pi_p[:len(nind)],
            linestyle="None",
            marker=mk,
            color=col,
            ms=4.0,
            mfc="white",
            mew=1.0,
            markevery=(i, 7),
            label=rf"$\delta={delta:.4g}$",
        )
    ax1.set_xlabel(r"mode index $n+1$  for $k_n=(2n+1)\pi/L$")
    ax1.set_ylabel(r"normalised excitation weight")
    ax1.legend(loc="best")
    ax1.text(0.04, 0.8, r"(a)", transform=ax1.transAxes, fontweight="bold")

    # PANEL (b) Counting ratio
    Rvals = []
    for delta in delta_grid:
        p = weak_quench_probabilities_h(h0, gamma, float(delta), L)
        Rvals.append(R_from_probabilities(p)[0])
    Rvals = np.array(Rvals)

    ax2.plot(delta_grid, Rvals, "o-", color=C["green"], ms=3.4, mfc="white", mew=0.9,
             label=r"$R(\delta)$")
    ax2.axhline(K_exact, color=C["red"], ls="--", lw=1.0, label=r"exact $K_F(h,L)$")
    ax2.set_xlabel(r"quench amplitude $\delta$")
    ax2.set_ylabel(r"extracted ratio $R(\delta)$")
    pad = max(0.005, 0.12 * (float(np.max(Rvals)) - float(np.min(Rvals)) + 1e-12))
    ax2.set_ylim(float(np.min(Rvals)) - pad, float(max(np.max(Rvals), K_exact)) + pad)
    ax2.legend(loc="best")
    ax2.text(0.04, 0.90, r"(b)", transform=ax2.transAxes, fontweight="bold")
    ax2.text(0.10, 0.10, rf"$h=h_c=1$, $L={L}$", transform=ax2.transAxes)

    fig.subplots_adjust(bottom=0.20, wspace=0.32)

    diagnostics["max |R(delta)-K_F| at smallest delta"] = float(abs(Rvals[0] - K_exact))
    diagnostics[f"{context.spec.display_name} exact K_F(h,L)"] = float(K_exact)
    diagnostics[f"{context.spec.display_name} <N>(delta_min)"] = float(R_from_probabilities(weak_quench_probabilities_h(h0, gamma, float(delta_grid[0]), L))[1])
    return FigureResult(fig, diagnostics)


# -----------------------------------------------------------------------------
# SINGLE runtime figure registry -- legacy output aliases are deliberately frozen
# -----------------------------------------------------------------------------
FIGURE_SPECS: tuple[FigureSpec, ...] = (
    FigureSpec(
        key="tfim_critical_concentration", selector="1",
        title="TFIM--XX response, ladders, and concentration",
        renderer=plot_fig1_tfim_critical_concentration,
        output_stem="fig1_tfim_critical_concentration", tex_label="fig:twothirds",
        tex_source="paper/main.tex",
        documents=(("paper/main.tex", "1"), ("arxiv-combined", "1")),
        panels=(("a", "Total-response scaling"), ("b", "Single/double soft ladders"),
                ("c", "Exact finite-size concentration")),
        parameter_group="tfim_critical_concentration",
    ),
    FigureSpec(
        key="scaling_and_envelope", selector="2", title="TFIM collapse and odd-ladder envelope",
        renderer=plot_fig2_scaling_and_envelope,
        output_stem="fig2_scaling_and_envelope", tex_label="fig:collapse",
        tex_source="paper/main.tex",
        documents=(("paper/main.tex", "2"), ("arxiv-combined", "2")),
        panels=(("a", "TFIM scaling collapse"), ("b", "Envelope versus exponent")),
        parameter_group="scaling_and_envelope",
    ),
    FigureSpec(
        key="lifshitz_anisotropy_scaling", selector="3", title="Lifshitz anisotropy and scaling",
        renderer=plot_fig3_lifshitz_anisotropy_scaling,
        output_stem="fig3_lifshitz_anisotropy_scaling", tex_label="fig:lifshitz",
        tex_source="paper/main.tex",
        documents=(("paper/main.tex", "3"), ("arxiv-combined", "3")),
        panels=(("a", "Two tangent directions at fixed L"), ("b", "Lifshitz scaling functions")),
        parameter_group="lifshitz_anisotropy_scaling",
    ),
    FigureSpec(
        key="interacting_benchmarks", selector="4", title="Potts and NNN-TFIM finite-size comparisons",
        renderer=plot_fig4_interacting_benchmarks,
        output_stem="fig6_interacting_benchmarks", tex_label="fig:interacting-benchmarks",
        tex_source="paper/main.tex",
        documents=(("paper/main.tex", "4"), ("arxiv-combined", "4")),
        panels=(("a", "Potts finite-size values and fixed references"),
                ("b", "NNN-TFIM versus exact TFIM")),
        data_inputs=("interacting_benchmarks.csv", "potts_outcome_aware_fss.csv",
                     "potts_theory_guided_7over5_receipt.json", "envelope_predictions_table.csv"),
        pad_inches=0.1,
    ),
    FigureSpec(
        key="ranked_response_distributions", selector="5", title="Potts and NNN-TFIM ranked weights",
        renderer=plot_fig5_distribution_comparisons,
        output_stem="figS1_potts_ideal_ladder_weights", tex_label="fig:potts-weight-comparators",
        tex_source="paper/main.tex",
        documents=(("paper/main.tex", "5"), ("arxiv-combined", "5")),
        panels=(("a", "Certified Potts ranks 1--15; inset ranks 2--15"),
                ("b", "NNN-TFIM and exact L=20 TFIM; inset ranks 2--10")),
        data_inputs=("potts_L14_certified_ranked_weights.csv",
                     "nnn_ranked_distribution_convergence.csv",
                     "nnn_ranked_distribution_convergence_receipt.json"),
        evidence_inputs=("cft/cft_kf_results.json",),
        pad_inches=0.1,
    ),
    FigureSpec(
        key="xy_directional_profiles", selector="6", title="XY directional profiles (main appendix)",
        renderer=plot_fig6_xy_directional_profiles,
        output_stem="fig4_xy_directional_profiles", tex_label="fig:xy-directional-profiles",
        tex_source="paper/main.tex",
        documents=(("paper/main.tex", "6"), ("arxiv-combined", "6")),
        panels=(("a", "Gapped XY polar profile"), ("b", "Regulated near-Lifshitz polar profile")),
        parameter_group="xy_directional_profiles",
    ),
    FigureSpec(
        key="weak_quench_extraction", selector="S1", title="Weak one-sided quench extraction",
        renderer=plot_figS1_weak_quench_extraction,
        output_stem="fig5_weak_quench_extraction", tex_label="fig:quench",
        tex_source="supplement_numerical/weak_quench_module.tex",
        documents=(("supplement_numerical/main.tex", "1"), ("arxiv-combined", "S1")),
        panels=(("a", "Normalized excitation weights"), ("b", "Counting ratio versus amplitude")),
        parameter_group="weak_quench_extraction",
    ),
)
# Derived views only: never duplicate the selector -> renderer/export mapping.
FIGURE_ORDER = tuple(spec.selector for spec in FIGURE_SPECS)


def get_figure_spec(identifier: str) -> FigureSpec:
    """Resolve a current selector, stable semantic key, or unique TeX label."""
    matches = [spec for spec in FIGURE_SPECS
               if identifier.upper() == spec.selector
               or identifier in (spec.key, spec.tex_label)]
    if len(matches) != 1:
        raise ValueError(f"unknown or ambiguous figure: {identifier!r}; selectors: {', '.join(FIGURE_ORDER)}")
    return matches[0]


# -----------------------------------------------------------------------------
# Read-only navigation and project-specific TeX binding validation
# -----------------------------------------------------------------------------
def _strip_tex_comments(text: str) -> str:
    # A percent is escaped only after an odd number of consecutive backslashes.
    return re.sub(r"(?m)(?<!\\)((?:\\\\)*)%[^\n]*", r"\1", text)


def _expand_tex_inputs(path: Path, root: Path, stack: tuple[Path, ...] = ()) -> str:
    """Expand literal project-local inputs only; reject cycles/unknown forms."""
    path = path.resolve()
    if not path.is_relative_to(root.resolve()) or path in stack:
        raise ValueError(f"unsafe or cyclic TeX input: {path}")
    text = _strip_tex_comments(path.read_text(encoding="utf-8"))
    pattern = re.compile(r"\\input\s*\{([^{}]+)\}")

    def expand(match: re.Match[str]) -> str:
        name = match.group(1)
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", name):
            raise ValueError(f"unsupported TeX input: {name!r}")
        child = path.parent / name
        if not child.suffix:
            child = child.with_suffix(".tex")
        return _expand_tex_inputs(child, root, (*stack, path))

    expanded = pattern.sub(expand, text)
    if re.search(r"\\(?:input|include)(?![A-Za-z])", expanded):
        raise ValueError(f"unsupported TeX input/include syntax in {path}")
    return expanded


def _scan_tex_figures(text: str) -> list[dict[str, str]]:
    """Parse ONLY this project's figure/counter syntax; never guess from names."""
    text = _strip_tex_comments(text)
    if re.search(r"\\(?:addtocounter|stepcounter|refstepcounter|counterwithin|numberwithin|counterwithout)\s*\{figure\}", text):
        raise ValueError("unsupported figure counter manipulation")
    # Remove exactly the supported counter commands; reject any remaining use.
    reset_pattern = r"\\setcounter\s*\{figure\}\s*\{(?P<reset>[0-9]+)\}"
    prefix_pattern = r"\\renewcommand\s*\{\\thefigure\}\s*\{(?P<prefix>S?)\\arabic\{figure\}\}"
    figure_pattern = r"\\begin\{(?P<environment>figure\*?)\}(?P<body>.*?)\\end\{(?P=environment)\}"
    pattern = re.compile(f"(?:{reset_pattern})|(?:{prefix_pattern})|(?:{figure_pattern})", re.DOTALL)
    residue = re.sub(reset_pattern, "", text)
    residue = re.sub(prefix_pattern, "", residue)
    if re.search(r"\\setcounter\s*\{figure\}|\\(?:re)?newcommand\s*\{?\\thefigure", residue):
        raise ValueError("unsupported figure number format/reset")
    records: list[dict[str, str]] = []
    number, prefix = 0, ""
    for match in pattern.finditer(text):
        if match.group("reset") is not None:
            number = int(match.group("reset"))
        elif match.group("prefix") is not None:
            prefix = match.group("prefix")
        else:
            body = match.group("body")
            labels = re.findall(r"\\label\s*\{([^{}]+)\}", body)
            images = re.findall(r"\\includegraphics\*?\s*(?:\[[^\]]*\])?\s*\{([^{}]+)\}", body)
            captions = re.findall(r"\\caption(?![A-Za-z])", body)
            ordinary_captions = re.findall(r"\\caption\s*(?:\[[^\]]*\]\s*)?\{", body)
            if len(labels) != 1 or len(images) != 1 or len(captions) != 1 or len(ordinary_captions) != 1:
                raise ValueError("each figure needs one literal label, image, and counter-incrementing caption")
            if not re.fullmatch(r"[A-Za-z0-9_-]+\.pdf", images[0]):
                raise ValueError(f"unsupported figure filename: {images[0]!r}")
            number += 1
            records.append({"label": labels[0], "stem": Path(images[0]).stem,
                            "number": f"{prefix}{number}"})
    if len(re.findall(r"\\begin\{figure\*?\}", text)) != len(records):
        raise ValueError("unmatched or unsupported figure environment")
    if len({r["label"] for r in records}) != len(records):
        raise ValueError("duplicate figure label in one document")
    return records


def validate_figure_mapping(project_root: Path | None = None) -> list[dict[str, str]]:
    """Validate source bindings without rendering, reading data, or writing files.

    The combined compositor is checked by the separate mapping verifier and
    compiled .aux acceptance; this read-only command checks both native source
    documents, including the standalone Supplement's literal input expansion.
    """
    root = project_root or Path(__file__).resolve().parents[2]
    for attribute in ("key", "selector", "output_stem", "renderer", "tex_label"):
        values = [getattr(spec, attribute) for spec in FIGURE_SPECS]
        if len(set(values)) != len(values):
            raise ValueError(f"duplicate registry {attribute}")
    for spec in FIGURE_SPECS:
        if not spec.renderer.__name__.startswith(f"plot_fig{spec.selector}_"):
            raise ValueError(f"{spec.display_name}: renderer name is not in current manuscript order")
        if not re.fullmatch(r"[A-Za-z0-9_]+", spec.output_stem):
            raise ValueError(f"invalid output alias: {spec.output_stem!r}")
        source_records = _scan_tex_figures(_expand_tex_inputs(root / spec.tex_source, root))
        matches = [record for record in source_records if record["label"] == spec.tex_label]
        if len(matches) != 1 or matches[0]["stem"] != spec.output_stem:
            raise ValueError(f"{spec.display_name}: label/output mismatch in {spec.tex_source}")
        source = inspect.getsource(spec.renderer)
        if f"Figure {spec.selector} ({spec.tex_label})" not in (spec.renderer.__doc__ or ""):
            raise ValueError(f"{spec.display_name}: stale renderer docstring")
        if "save_figure(" in source or "save_named_figure(" in source or ".savefig(" in source:
            raise ValueError(f"{spec.display_name}: renderer must not own output selection")
    reports: list[dict[str, str]] = []
    documents = sorted({document for spec in FIGURE_SPECS for document, _ in spec.documents
                        if document != "arxiv-combined"})
    for document in documents:
        actual = _scan_tex_figures(_expand_tex_inputs(root / document, root))
        expected = [dict(label=spec.tex_label, stem=spec.output_stem, number=number)
                    for spec in FIGURE_SPECS for doc, number in spec.documents if doc == document]
        if actual != expected:
            raise ValueError(f"figure mapping mismatch in {document}: expected {expected!r}; observed {actual!r}")
        reports.extend({"document": document, **record} for record in actual)
    return reports


def _input_paths(spec: FigureSpec, data_dir: Path, evidence_dir: Path) -> tuple[Path, ...]:
    return tuple(data_dir / name for name in spec.data_inputs) + tuple(
        evidence_dir / name for name in spec.evidence_inputs)


def validate_selected_inputs(specs: Sequence[FigureSpec], data_dir: Path, evidence_dir: Path) -> None:
    """Check every selected file BEFORE any renderer writes an output pair."""
    missing = [f"{spec.display_name} [{spec.key}]: {path}"
               for spec in specs for path in _input_paths(spec, data_dir, evidence_dir)
               if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing figure input(s):\n" + "\n".join(missing))


def figure_description(spec: FigureSpec, outdir: Path, data_dir: Path, evidence_dir: Path) -> dict:
    """Machine-readable navigation, separate from scientific diagnostics."""
    return {
        "selector": spec.selector, "key": spec.key, "title": spec.title,
        "renderer": spec.renderer.__name__,
        "renderer_source": "scripts/plotting/generate_figures.py",
        "renderer_line": spec.renderer.__code__.co_firstlineno,
        "tex_label": spec.tex_label, "tex_source": spec.tex_source,
        "document_numbers": dict(spec.documents), "legacy_output_alias": spec.output_stem,
        "panels": dict(spec.panels), "parameter_group": spec.parameter_group,
        "data_inputs": [str(data_dir / name) for name in spec.data_inputs],
        "evidence_inputs": [str(evidence_dir / name) for name in spec.evidence_inputs],
        "outputs": [str(outdir / f"{spec.output_stem}.{suffix}") for suffix in ("pdf", "png")],
        "export": {"png_dpi": 300, "bbox_inches": None, "pad_inches": None},
    }


def _print_description(spec: FigureSpec, outdir: Path, data_dir: Path, evidence_dir: Path) -> None:
    description = figure_description(spec, outdir, data_dir, evidence_dir)
    print(f"{spec.display_name}: {spec.title}")
    print(f"  stable key: {spec.key}")
    print(f"  renderer: {description['renderer_source']}:{description['renderer_line']} :: {spec.renderer.__name__}")
    print(f"  TeX: {spec.tex_source} :: {spec.tex_label}")
    for document, number in spec.documents:
        print(f"  document: {document} -> Figure {number}")
    for panel, role in spec.panels:
        print(f"  panel ({panel}): {role}")
    print(f"  parameter group: {spec.parameter_group or 'released tables / evidence'}")
    for path in _input_paths(spec, data_dir, evidence_dir):
        print(f"  input: {path}")
    print(f"  legacy output alias (not the current figure number): {spec.output_stem}")
    for path in description["outputs"]:
        print(f"  output: {path}")


# -----------------------------------------------------------------------------
# Main driver -- selection and export both use the same FigureSpec
# -----------------------------------------------------------------------------
def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["fast", "publication"], default="publication",
                        help="Parameter preset. 'fast' is for quick checks; 'publication' uses denser grids.")
    parser.add_argument("--fig", type=lambda value: value.upper(), nargs="+", choices=FIGURE_ORDER,
                        help="Generate selected figures in manuscript order: 1 2 3 4 5 6 S1.")
    parser.add_argument("--all", action="store_true", help="Generate all figures (takes priority over --fig).")
    query = parser.add_mutually_exclusive_group()
    query.add_argument("--list", dest="list_figures", action="store_true", help="List figure/renderer/output bindings; do not render.")
    query.add_argument("--describe", metavar="FIGURE", help="Describe a selector, stable key, or TeX label; do not render.")
    query.add_argument("--check-map", action="store_true", help="Check native TeX figure bindings read-only; no input data required.")
    parser.add_argument("--outdir", type=str, default=None,
                        help="PDF/PNG directory. Default: <project>/build/regenerated_figures.")
    parser.add_argument("--allow-canonical-output", action="store_true",
                        help="Explicitly allow writing to frozen <project>/figures; never implied by a query.")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Input table root. Default: <project>/data/reproducibility.")
    parser.add_argument("--evidence-dir", type=str, default=None,
                        help="Independent evidence root. Default: <project>/repro/evidence; NOT inferred from --data-dir.")
    parser.add_argument("--diagnostics-output", type=str, default=None,
                        help="Scientific diagnostics text path (existing format is preserved).")
    parser.add_argument("--mapping-output", type=str, default=None,
                        help="Separate JSON navigation receipt. Default: <project>/build/receipts/figure_mapping_<mode>_<ids>.json.")
    args = parser.parse_args(argv)
    if (args.list_figures or args.describe is not None or args.check_map) and (args.all or args.fig):
        parser.error("read-only query options cannot be combined with --fig or --all")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parents[2]
    # Resolve without validation first: navigation must work with absent data.
    outdir = Path(args.outdir).resolve() if args.outdir else project_root / "build/regenerated_figures"
    data_dir = Path(args.data_dir).resolve() if args.data_dir else project_root / "data/reproducibility"
    evidence_dir = Path(args.evidence_dir).resolve() if args.evidence_dir else project_root / "repro/evidence"
    if args.list_figures:
        for spec in FIGURE_SPECS:
            print(f"{spec.selector:>2} | {spec.title}\n   {spec.renderer.__name__}\n   legacy alias: {spec.output_stem}")
        print("S1 is Figure 1 in the standalone Supplement and Figure S1 in arxiv-combined.")
        return
    if args.describe is not None:
        _print_description(get_figure_spec(args.describe), outdir, data_dir, evidence_dir)
        print(f"  manuscript reads frozen artwork from: {project_root / 'figures'}")
        return
    if args.check_map:
        for record in validate_figure_mapping(project_root):
            print(f"[PASS] {record['document']} Figure {record['number']}: {record['label']} -> {record['stem']}")
        print("[PASS] native source mapping; no figures, fits, or simulations were generated.")
        return

    if args.all or not args.fig:
        targets = list(FIGURE_SPECS)
    else:
        selected = set(args.fig)
        targets = [spec for spec in FIGURE_SPECS if spec.selector in selected]
    # Validate all source bindings before any output; do not let a wrong mapping
    # silently write a scientifically different figure under a valid filename.
    validate_figure_mapping(project_root)
    outdir, data_dir = default_paths(args.outdir, args.data_dir,
                                    allow_canonical_output=args.allow_canonical_output)
    validate_selected_inputs(targets, data_dir, evidence_dir)
    params = get_params(args.mode)
    configure_plotting()
    diagnostics: dict[str, float | int] = {}
    print(f"Mode: {args.mode}")
    print(f"Output figures directory: {outdir}")
    print(f"Manuscript reads frozen artwork from: {project_root / 'figures'}")
    print(f"Data directory: {data_dir}")
    print(f"Evidence directory (independent of data): {evidence_dir}")
    print(f"Generating figures: {[spec.selector for spec in targets]}\n")
    descriptions: list[dict] = []
    for spec in targets:
        print(f"[{spec.display_name}] key={spec.key}; renderer={spec.renderer.__name__}; "
              f"label={spec.tex_label}; legacy_alias={spec.output_stem}; mode={args.mode}")
        context = PlotContext(spec, params, project_root, data_dir, evidence_dir)
        existing_figures = set(plt.get_fignums())
        try:
            result = spec.renderer(context)
            save_figure(result.figure, spec, outdir)
            diagnostics.update(result.diagnostics)
            descriptions.append(figure_description(spec, outdir, data_dir, evidence_dir))
        finally:
            # Close this renderer's figures even when a data guard/export fails.
            for figure_number in set(plt.get_fignums()) - existing_figures:
                plt.close(figure_number)

    ids = "all" if len(targets) == len(FIGURE_SPECS) else "-".join(spec.selector for spec in targets)
    diag_path = (Path(args.diagnostics_output).resolve() if args.diagnostics_output else
                 project_root / "build/receipts" / f"figure_diagnostics_{args.mode}_{ids}.txt")
    diag_path.parent.mkdir(parents=True, exist_ok=True)
    with diag_path.open("w", encoding="utf-8") as handle:
        for key, value in diagnostics.items():
            handle.write(f"{key} = {value}\n")
    mapping_path = (Path(args.mapping_output).resolve() if args.mapping_output else
                    project_root / "build/receipts" / f"figure_mapping_{args.mode}_{ids}.json")
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text(json.dumps({
        "schema": "channel-concentration-figure-map/1.0", "mode": args.mode,
        "figures": descriptions, "scientific_diagnostics": str(diag_path),
        "canonical_figure_root": str(project_root / "figures"),
        "output_root": str(outdir),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nDiagnostics\n-----------")
    for key, value in diagnostics.items():
        print(f"{key} = {value}")
    print(f"wrote {diag_path}")
    print(f"wrote separate mapping receipt {mapping_path}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(f"error: {exc}") from exc
