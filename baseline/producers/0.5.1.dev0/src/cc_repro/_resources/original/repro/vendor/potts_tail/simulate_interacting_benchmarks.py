#!/usr/bin/env python3
"""Exact-diagonalization benchmarks for channel concentration in Potts and NNN-TFIM.

This standalone script computes the level-projector channel weights

    x_a = ||Pi_a V |0>||^2 / (E_a - E_0)^2,
    K_F = sum_a x_a^2 / (sum_a x_a)^2,

where degenerate eigenstates are grouped into a single level projector Pi_a.
The maximum intended system size is L=12 for Potts.  For the NNN-TFIM control,
the default response calculation uses the translation-invariant,
global-spin-flip-even sector, which makes the L=16,18,20 calculations feasible
    without full Hilbert-space diagonalization.  The J2=0 NNN-TFIM reference is
    written from the exact critical TFIM finite-size formula when no fixed --nnn-h
    is supplied; verify_j2_zero_resolution.py independently matches that curve
    to the level-projector ED path at small sizes.

Examples
--------
# Reproduce the manuscript benchmark CSV in one command
# (Potts k=0 for L=6..12 and the NNN-TFIM control J2={0,0.05,0.10,0.20}
#  for even L=6..20 using the sector method and a PRG-field table):
python simulate_interacting_benchmarks.py --models potts,nnn \
    --Lmin 6 --Lmax 12 --nnn-Lmax 20 --nnn-method sector \
    --nnn-h-table data/reproducibility/nnn_tfim_prg_fields_L20.csv

# Only the NNN-TFIM control to L=20 using the symmetry sector:
python simulate_interacting_benchmarks.py --models nnn --Lmin 6 --nnn-Lmax 20 \
    --nnn-method sector --nnn-h-table data/reproducibility/nnn_tfim_prg_fields_L20.csv
"""
from __future__ import annotations

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse
import csv
import functools
import math
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import scipy.linalg as la
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.optimize import brentq


# ---------------------------------------------------------------------------
# Generic level-projector channel concentration
# ---------------------------------------------------------------------------

def group_level_weights(evals: np.ndarray, amplitudes2: np.ndarray, E0: float,
                        tol_group: float = 1e-7) -> np.ndarray:
    """Group degenerate levels and return x_a = sum_m |c_m|^2 / gap_a^2."""
    order = np.argsort(evals)
    ev = np.asarray(evals)[order]
    w = np.asarray(amplitudes2)[order]
    xs: list[float] = []
    i = 0
    while i < len(ev):
        j = i + 1
        while j < len(ev) and ev[j] - ev[i] <= tol_group:
            j += 1
        gap = float(ev[i:j].mean() - E0)
        if gap > tol_group:
            xs.append(float(w[i:j].sum() / gap**2))
        i = j
    return np.asarray(xs, dtype=float)


def dense_level_projector_kf(H: np.ndarray, dH: np.ndarray,
                             tol_group: float = 1e-7) -> dict:
    """Full spectral result.  Only use for small validation sizes."""
    evals, evecs = la.eigh(H)
    E0 = float(evals[0])
    psi0 = evecs[:, 0]
    b = dH @ psi0
    b = b - float(psi0 @ b) * psi0
    amps2 = np.abs(evecs.T @ b) ** 2
    xs = group_level_weights(evals, amps2, E0, tol_group)
    P2 = float(xs.sum())
    P4 = float(np.sum(xs**2))
    gap = float(evals[1] - evals[0])
    return {
        "KF": P4 / P2**2,
        "P2": P2,
        "P4": P4,
        "gap": gap,
        "solve_res": 0.0,
        "n_levels": len(xs),
        "x": np.sort(xs)[::-1],
    }


def hybrid_level_projector_kf(H: sp.spmatrix, dH: sp.spmatrix, k_low: int = 96,
                              tol_eig: float = 1e-9,
                              tol_group: float = 1e-7,
                              rtol_solve: float = 1e-9,
                              ncv_factor: int = 4) -> dict:
    """Hybrid estimator: exact P2 from a projected linear solve, P4 from low levels.

    P2 is obtained from (H-E0)y = Q V|0>, P2=||y||^2.  To remove the null
    vector numerically, the solved operator is augmented by alpha |0><0|.
    The solution is unchanged because the right-hand side is orthogonal to |0>.
    """
    H = H.tocsr()
    dH = dH.tocsr()
    dim = H.shape[0]
    # A moderately oversized Krylov subspace is important in the symmetry
    # sector near criticality.  Small ncv values can make ARPACK stall for
    # L=20 even when the target sector dimension is only O(10^4).
    ncv0 = min(dim - 1, max(60, ncv_factor * min(k_low, dim - 2)))
    grid = np.arange(1, dim + 1, dtype=float)
    v0 = np.cos(0.6180339887498949 * grid) + 0.5 * np.sin(0.4142135623730950 * grid)
    v0 /= np.linalg.norm(v0)
    ev0, ec0 = spla.eigsh(H, k=2, which="SA", tol=tol_eig, ncv=ncv0, v0=v0)
    order = np.argsort(ev0)
    E0 = float(ev0[order[0]])
    psi0 = ec0[:, order[0]]
    gap = float(ev0[order[1]] - ev0[order[0]])

    b = dH @ psi0
    b = b - float(psi0 @ b) * psi0
    A = (H - E0 * sp.identity(dim, format="csr")).tocsr()
    alpha = max(gap, 1e-6)
    Aop = spla.LinearOperator(
        (dim, dim),
        matvec=lambda v: A @ v + alpha * psi0 * float(psi0 @ v),
        dtype=float,
    )
    y, info = spla.minres(Aop, b, rtol=rtol_solve, maxiter=30000)
    y = y - float(psi0 @ y) * psi0
    P2 = float(y @ y)
    solve_res = float(np.linalg.norm(A @ y - b) / max(np.linalg.norm(b), 1e-300))

    k = min(k_low, dim - 2)
    ncv_low = min(dim - 1, max(80, ncv_factor * k + 1))
    ev, ec = spla.eigsh(H, k=k, which="SA", tol=tol_eig, ncv=ncv_low, v0=v0)
    order = np.argsort(ev)
    ev = ev[order]
    ec = ec[:, order]
    amps2 = np.abs(ec.T @ b) ** 2
    xs = group_level_weights(ev, amps2, E0, tol_group)
    P4 = float(np.sum(xs**2))
    KF = P4 / P2**2

    # Low-level convergence diagnostic: recompute P4 using the first half.
    m_half = max(4, len(ev) // 2)
    xs_half = group_level_weights(ev[:m_half], amps2[:m_half], E0, tol_group)
    P4_half = float(np.sum(xs_half**2))

    return {
        "KF": KF,
        "KF_half": P4_half / P2**2,
        "P2": P2,
        "P4": P4,
        "gap": gap,
        "solve_res": solve_res,
        "minres_info": int(info),
        "n_levels": len(xs),
        "x": np.sort(xs)[::-1],
    }


# ---------------------------------------------------------------------------
# Model builders
# ---------------------------------------------------------------------------

def build_potts_full(L: int, g: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Full standard 3-state Potts Hamiltonian in the clock basis.

    The diagonal term is -g sum_j (sigma_j^dagger sigma_{j+1}+h.c.); the
    off-diagonal cyclic shifts are -sum_j (tau_j+tau_j^dagger).  The returned
    dH is the thermal interaction representative dH/dg.
    """
    dim = 3**L
    states = np.arange(dim, dtype=np.int64)
    digits = np.zeros((dim, L), dtype=np.int8)
    tmp = states.copy()
    for i in range(L):
        digits[:, i] = tmp % 3
        tmp //= 3

    V = np.zeros(dim, dtype=float)
    for i in range(L):
        j = (i + 1) % L
        V += 2.0 * np.cos(2.0 * np.pi * ((digits[:, i] - digits[:, j]) % 3) / 3.0)

    powers = np.array([3**i for i in range(L)], dtype=np.int64)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    for i in range(L):
        ai = digits[:, i].astype(np.int64)
        for delta in (1, 2):
            rows.append(states)
            cols.append(states + (((ai + delta) % 3) - ai) * powers[i])
    T = sp.coo_matrix(
        (np.ones(2 * L * dim), (np.concatenate(rows), np.concatenate(cols))),
        shape=(dim, dim),
    ).toarray()
    H = -T - g * np.diag(V)
    dH = -np.diag(V)
    return H, dH


def _translate_base3(states: np.ndarray, L: int) -> np.ndarray:
    """Cyclic translation of base-3 encoded spin configurations."""
    return 3 * states - (states // (3 ** (L - 1))) * (3**L - 1)


@functools.lru_cache(maxsize=None)
def _potts_translation_orbits(
    L: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return representatives, orbit sizes, state-to-orbit map, and digits.

    This helper defines the full translation-invariant ``k=0`` basis.  It does
    not project onto a Potts ``Z3`` charge sector; that second reduction is
    constructed independently by :func:`build_potts_k0_q0`.
    """
    dim_full = 3**L
    states = np.arange(dim_full, dtype=np.int64)
    representative = states.copy()
    translated = states.copy()
    for _ in range(L - 1):
        translated = _translate_base3(translated, L)
        representative = np.minimum(representative, translated)

    reps, orbit_size = np.unique(representative, return_counts=True)
    rep_to_index = {int(rep): index for index, rep in enumerate(reps)}
    state_to_orbit = np.fromiter(
        (rep_to_index[int(rep)] for rep in representative),
        dtype=np.int64,
        count=dim_full,
    )

    digits = np.zeros((len(reps), L), dtype=np.int8)
    tmp = reps.copy()
    for site in range(L):
        digits[:, site] = tmp % 3
        tmp //= 3
    return reps, orbit_size, state_to_orbit, digits


def build_potts_k0(L: int, g: float = 1.0) -> tuple[sp.csr_matrix, sp.csr_matrix, int]:
    """Standard 3-state Potts Hamiltonian in the translation-invariant k=0 sector.

    Uses sigma as the clock/order operator and tau as the shift/transverse-field
    operator.  The returned dH is -sum_j(sigma_j^dagger sigma_{j+1}+h.c.).
    """
    reps, orbit_size, state_to_orbit, digits = _potts_translation_orbits(L)
    nrep = len(reps)
    sqrt_orbit = np.sqrt(orbit_size.astype(float))

    V = np.zeros(nrep, dtype=float)
    for i in range(L):
        j = (i + 1) % L
        V += 2.0 * np.cos(2.0 * np.pi * ((digits[:, i] - digits[:, j]) % 3) / 3.0)

    powers = np.array([3**i for i in range(L)], dtype=np.int64)
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    for col in range(nrep):
        r = int(reps[col])
        a = digits[col].astype(np.int64)
        for i in range(L):
            for delta in (1, 2):
                snew = r + (((a[i] + delta) % 3) - a[i]) * int(powers[i])
                row = int(state_to_orbit[snew])
                rows.append(row)
                cols.append(col)
                vals.append(sqrt_orbit[col] / sqrt_orbit[row])
    T = sp.coo_matrix((vals, (rows, cols)), shape=(nrep, nrep)).tocsr()
    H = (-T - g * sp.diags(V, format="csr")).tocsr()
    dH = (-sp.diags(V, format="csr")).tocsr()
    return H, dH, nrep


def potts_k0_color_shift(L: int) -> sp.csr_matrix:
    """Global color-shift operator in the full translation ``k=0`` basis.

    With ``sigma|m>=omega^m|m>`` and ``tau|m>=|m+1 mod 3>``, the symmetry
    generator is ``C=prod_j tau_j``.  The returned real permutation matrix
    obeys ``C**3=I`` and commutes with both the Potts Hamiltonian and the
    thermal perturbation.
    """
    reps, orbit_size, state_to_orbit, digits = _potts_translation_orbits(L)
    powers = np.array([3**site for site in range(L)], dtype=np.int64)
    shifted_states = np.sum(((digits.astype(np.int64) + 1) % 3) * powers, axis=1)
    shifted_orbits = state_to_orbit[shifted_states]
    if not np.array_equal(orbit_size, orbit_size[shifted_orbits]):
        raise RuntimeError("global color shift changed a translation-orbit size")
    columns = np.arange(len(reps), dtype=np.int64)
    return sp.coo_matrix(
        (np.ones(len(reps), dtype=float), (shifted_orbits, columns)),
        shape=(len(reps), len(reps)),
    ).tocsr()


def potts_k0_q0_isometry(L: int) -> sp.csr_matrix:
    """Isometry whose columns span the explicit ``(k=0,q=0)`` subspace."""
    color_shift = potts_k0_color_shift(L)
    shift_index = np.asarray(color_shift.argmax(axis=0)).ravel()
    visited = np.zeros(color_shift.shape[0], dtype=bool)
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    column = 0
    for start in range(color_shift.shape[0]):
        if visited[start]:
            continue
        cycle: list[int] = []
        current = start
        while not visited[current]:
            visited[current] = True
            cycle.append(current)
            current = int(shift_index[current])
        if current != start or len(cycle) not in (1, 3):
            raise RuntimeError("invalid global-color-shift orbit in k=0 basis")
        normalization = 1.0 / math.sqrt(len(cycle))
        rows.extend(cycle)
        cols.extend([column] * len(cycle))
        vals.extend([normalization] * len(cycle))
        column += 1
    return sp.coo_matrix(
        (vals, (rows, cols)), shape=(color_shift.shape[0], column)
    ).tocsr()


def build_potts_k0_q0(
    L: int, g: float = 1.0
) -> tuple[sp.csr_matrix, sp.csr_matrix, sp.csr_matrix]:
    """Potts Hamiltonian in the explicit translation- and charge-neutral block.

    Returns ``(H_q0,dH_q0,S)`` with ``S`` the isometry from the explicit
    ``q=0`` basis into the full ``k=0`` translation basis.
    """
    H_k0, dH_k0, _ = build_potts_k0(L, g)
    isometry = potts_k0_q0_isometry(L)
    H_q0 = (isometry.T @ H_k0 @ isometry).tocsr()
    dH_q0 = (isometry.T @ dH_k0 @ isometry).tocsr()
    return H_q0, dH_q0, isometry


def potts_q0_leakage(vector: np.ndarray, L: int) -> float:
    """Relative norm outside charge ``q=0`` for a vector in the ``k=0`` basis."""
    vector = np.asarray(vector)
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        return 0.0
    color_shift = potts_k0_color_shift(L)
    projected = (vector + color_shift @ vector + color_shift @ (color_shift @ vector)) / 3.0
    return float(np.linalg.norm(vector - projected) / norm)


def build_nnn_tfim_components(L: int, lam: float) -> tuple[sp.csr_matrix, sp.csr_matrix]:
    """Return (H_zz, X) in the full spin basis for the NNN-TFIM."""
    dim = 1 << L
    states = np.arange(dim, dtype=np.int64)
    diag = np.zeros(dim, dtype=float)
    for i in range(L):
        zi = 1 - 2 * ((states >> i) & 1)
        zj = 1 - 2 * ((states >> ((i + 1) % L)) & 1)
        zk = 1 - 2 * ((states >> ((i + 2) % L)) & 1)
        diag += zi * zj + lam * zi * zk

    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    for i in range(L):
        rows.append(states)
        cols.append(states ^ (1 << i))
    X = sp.coo_matrix(
        (np.ones(L * dim), (np.concatenate(rows), np.concatenate(cols))),
        shape=(dim, dim),
    ).tocsr()
    Hzz = sp.diags(-diag, format="csr")
    return Hzz, X


def build_nnn_tfim(L: int, h: float, lam: float) -> tuple[sp.csr_matrix, sp.csr_matrix]:
    """H = -sum ZZ_1 - lam sum ZZ_2 - h sum X, with PBC; dH/dh=-sum X."""
    Hzz, X = build_nnn_tfim_components(L, lam)
    H = (Hzz - h * X).tocsr()
    dH = (-X).tocsr()
    return H, dH


def _translate_bits(state: int, L: int, mask: int) -> int:
    """Translate a binary spin configuration by one site."""
    return ((state << 1) & mask) | (state >> (L - 1))


def _orbit_rep_binary(state: int, L: int, mask: int) -> int:
    """Representative of the orbit generated by translation and global flip."""
    best = state
    s = state
    sf = state ^ mask
    for _ in range(L):
        if s < best:
            best = s
        if sf < best:
            best = sf
        s = _translate_bits(s, L, mask)
        sf = _translate_bits(sf, L, mask)
    return int(best)


def _binary_orbits_translation_spinflip(L: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return representatives, orbit sizes, and full-state-to-rep-index map.

    The orbit group is generated by one-site translation and global spin flip.
    The resulting orbit basis spans the k=0, global-spin-flip-even sector.  This
    is the physical response sector for the NNN-TFIM transverse-field tuning,
    because both H and dH/dh=-sum_i X_i preserve translation and global spin
    flip.
    """
    dim_full = 1 << L
    mask = dim_full - 1
    reps_full = np.empty(dim_full, dtype=np.int64)
    for s in range(dim_full):
        reps_full[s] = _orbit_rep_binary(s, L, mask)
    reps, inverse, orbit_size = np.unique(reps_full, return_inverse=True, return_counts=True)
    return reps.astype(np.int64), orbit_size.astype(np.int64), inverse.astype(np.int64)


@functools.lru_cache(maxsize=32)
def _binary_translation_parity_maps(
    L: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return normalized-orbit maps for the k=0 even and odd parity sectors.

    Translation orbits are paired by the global spin flip ``F=prod_i X_i``.
    An even basis vector is the normalized sum over the union of a translation
    orbit and its flipped partner.  The corresponding odd vector has opposite
    signs on the two partners.  Translation orbits that are invariant under
    the flip contribute only to the even sector.

    The returned arrays are ``(reps_e, sizes_e, index_e, reps_o, sizes_o,
    index_o, sign_o)``.  ``index_*`` maps every full-basis state to a reduced
    basis index; absent odd states carry index ``-1``.  ``sign_o`` is ``+1`` or
    ``-1`` on the two members of an odd orbit pair and zero on absent states.
    """
    if L < 2:
        raise ValueError("translation/parity sectors require L >= 2")
    dim_full = 1 << L
    mask = dim_full - 1
    states = np.arange(dim_full, dtype=np.int64)

    translation_rep = np.empty(dim_full, dtype=np.int64)
    for state in range(dim_full):
        best = state
        shifted = state
        for _ in range(1, L):
            shifted = _translate_bits(shifted, L, mask)
            if shifted < best:
                best = shifted
        translation_rep[state] = best

    flipped_rep = translation_rep[states ^ mask]
    canonical = np.minimum(translation_rep, flipped_rep)

    reps_e, index_e, sizes_e = np.unique(
        canonical, return_inverse=True, return_counts=True
    )

    odd_valid = translation_rep != flipped_rep
    reps_o, inverse_o, sizes_o = np.unique(
        canonical[odd_valid], return_inverse=True, return_counts=True
    )
    index_o = np.full(dim_full, -1, dtype=np.int64)
    index_o[odd_valid] = inverse_o
    sign_o = np.zeros(dim_full, dtype=np.int8)
    sign_o[odd_valid] = np.where(
        translation_rep[odd_valid] == canonical[odd_valid], 1, -1
    )

    return (
        reps_e.astype(np.int64),
        sizes_e.astype(np.int64),
        index_e.astype(np.int64),
        reps_o.astype(np.int64),
        sizes_o.astype(np.int64),
        index_o,
        sign_o,
    )


@functools.lru_cache(maxsize=32)
def _nnn_tfim_k0_parity_x(L: int, parity: int) -> tuple[np.ndarray, sp.csr_matrix]:
    """Return orbit representatives and ``X=sum_i X_i`` for one parity sector."""
    if parity not in (-1, 1):
        raise ValueError("parity must be +1 (even) or -1 (odd)")
    maps = _binary_translation_parity_maps(L)
    if parity == 1:
        reps, orbit_size, inverse = maps[0], maps[1], maps[2]
        signs = np.ones(1 << L, dtype=np.int8)
    else:
        reps, orbit_size, inverse, signs = maps[3], maps[4], maps[5], maps[6]

    dim_full = 1 << L
    states = np.arange(dim_full, dtype=np.int64)
    valid_col = inverse >= 0
    sqrt_orbit = np.sqrt(orbit_size.astype(float))
    row_parts: list[np.ndarray] = []
    col_parts: list[np.ndarray] = []
    val_parts: list[np.ndarray] = []
    for i in range(L):
        flipped = states ^ (1 << i)
        valid = valid_col & (inverse[flipped] >= 0)
        cols = inverse[valid]
        rows = inverse[flipped[valid]]
        vals = (
            signs[valid].astype(float)
            * signs[flipped[valid]].astype(float)
            / (sqrt_orbit[cols] * sqrt_orbit[rows])
        )
        row_parts.append(rows)
        col_parts.append(cols)
        val_parts.append(vals)
    X = sp.coo_matrix(
        (np.concatenate(val_parts), (np.concatenate(row_parts), np.concatenate(col_parts))),
        shape=(len(reps), len(reps)),
    ).tocsr()
    X.sum_duplicates()
    return reps, X


def build_nnn_tfim_sector_components_k0_parity(
    L: int, lam: float, parity: int
) -> tuple[sp.csr_matrix, sp.csr_matrix, int]:
    """Return ``(H_zz, X, dim)`` in the k=0 spin-flip parity sector.

    ``parity=+1`` selects the even response sector and ``parity=-1`` the odd
    sector needed for the finite-size symmetry gap.  The construction is an
    exact normalized projection of the full periodic spin Hamiltonian.
    """
    reps, X = _nnn_tfim_k0_parity_x(L, parity)
    diag = np.zeros(len(reps), dtype=float)
    for i in range(L):
        zi = 1 - 2 * ((reps >> i) & 1)
        zj = 1 - 2 * ((reps >> ((i + 1) % L)) & 1)
        zk = 1 - 2 * ((reps >> ((i + 2) % L)) & 1)
        diag += zi * zj + lam * zi * zk
    return sp.diags(-diag, format="csr"), X, len(reps)


def lowest_sector_energy(
    Hzz: sp.csr_matrix,
    X: sp.csr_matrix,
    h: float,
    tol: float = 1e-10,
    maxiter: int = 100_000,
) -> tuple[float, float]:
    """Return the lowest energy and relative eigenpair residual deterministically."""
    H = (Hzz - h * X).tocsr()
    dim = H.shape[0]
    if dim <= 4:
        evals, evecs = la.eigh(H.toarray())
        energy = float(evals[0])
        vector = np.asarray(evecs[:, 0], dtype=float)
    else:
        grid = np.arange(1, dim + 1, dtype=float)
        v0 = np.cos(0.6180339887498949 * grid) + 0.5 * np.sin(0.4142135623730950 * grid)
        v0 /= np.linalg.norm(v0)
        evals, evecs = spla.eigsh(
            H,
            k=1,
            which="SA",
            tol=tol,
            maxiter=maxiter,
            ncv=min(dim - 1, max(30, min(120, dim // 2))),
            v0=v0,
        )
        energy = float(evals[0])
        vector = np.asarray(evecs[:, 0], dtype=float)
    residual = float(np.linalg.norm(H @ vector - energy * vector) / max(1.0, abs(energy)))
    return energy, residual


def parity_gap_nnn_from_components(
    even_components: tuple[sp.csr_matrix, sp.csr_matrix, int],
    odd_components: tuple[sp.csr_matrix, sp.csr_matrix, int],
    h: float,
    tol: float = 1e-10,
) -> dict[str, float]:
    """Return the k=0 odd-even spin-flip gap and solver diagnostics."""
    e_even, res_even = lowest_sector_energy(even_components[0], even_components[1], h, tol)
    e_odd, res_odd = lowest_sector_energy(odd_components[0], odd_components[1], h, tol)
    gap = e_odd - e_even
    if gap <= 0.0:
        raise RuntimeError(f"non-positive odd-even parity gap at h={h:.16g}: {gap:.6e}")
    return {
        "gap": float(gap),
        "energy_even": float(e_even),
        "energy_odd": float(e_odd),
        "residual_even": float(res_even),
        "residual_odd": float(res_odd),
        "dim_even": float(even_components[2]),
        "dim_odd": float(odd_components[2]),
    }


def parity_gap_nnn(L: int, h: float, lam: float, tol: float = 1e-10) -> dict[str, float]:
    """Build both k=0 parity sectors and return their lowest-energy gap."""
    even = build_nnn_tfim_sector_components_k0_parity(L, lam, +1)
    odd = build_nnn_tfim_sector_components_k0_parity(L, lam, -1)
    return parity_gap_nnn_from_components(even, odd, h, tol)


def build_nnn_tfim_sector_components_k0_even(L: int, lam: float) -> tuple[sp.csr_matrix, sp.csr_matrix, int]:
    """Return (H_zz, X, dim) in the k=0, global-spin-flip-even sector.

    The Hamiltonian at field h is H(h)=H_zz-h X and dH/dh=-X.
    Keeping the h-independent components separate is important for PRG scans,
    where many trial fields are tested at the same (L, J2).
    """
    dim_full = 1 << L
    reps, orbit_size, inverse = _binary_orbits_translation_spinflip(L)
    nrep = len(reps)
    sqrt_orbit = np.sqrt(orbit_size.astype(float))

    # Diagonal Ising part is constant on each orbit.
    diag = np.zeros(nrep, dtype=float)
    for i in range(L):
        zi = 1 - 2 * ((reps >> i) & 1)
        zj = 1 - 2 * ((reps >> ((i + 1) % L)) & 1)
        zk = 1 - 2 * ((reps >> ((i + 2) % L)) & 1)
        diag += zi * zj + lam * zi * zk

    # Build X=sum_i X_i by summing all full-basis transitions and projecting
    # them to orbit states.  For normalized orbit states |O_a>, the matrix
    # element is the transition count divided by sqrt(|O_a||O_b|).
    rows = np.empty(dim_full * L, dtype=np.int64)
    cols = np.empty(dim_full * L, dtype=np.int64)
    vals = np.empty(dim_full * L, dtype=float)
    idx = 0
    for s in range(dim_full):
        col = inverse[s]
        denom_col = sqrt_orbit[col]
        for i in range(L):
            row = inverse[s ^ (1 << i)]
            rows[idx] = row
            cols[idx] = col
            vals[idx] = 1.0 / (denom_col * sqrt_orbit[row])
            idx += 1
    X = sp.coo_matrix((vals, (rows, cols)), shape=(nrep, nrep)).tocsr()
    Hzz = sp.diags(-diag, format="csr")
    return Hzz, X, nrep


def build_nnn_tfim_sector_k0_even(L: int, h: float, lam: float) -> tuple[sp.csr_matrix, sp.csr_matrix, int]:
    """NNN-TFIM in the k=0, global-spin-flip-even orbit basis.

    Basis vectors are normalized equal-weight sums over orbits of the group
    generated by translation and global spin flip.  The reduced Hamiltonian is
    exactly the restriction of

        H = -sum_i Z_i Z_{i+1} - lam sum_i Z_i Z_{i+2} - h sum_i X_i

    to this sector, and dH is -sum_i X_i in the same basis.
    """
    Hzz, X, nrep = build_nnn_tfim_sector_components_k0_even(L, lam)
    H = (Hzz - h * X).tocsr()
    dH = (-X).tocsr()
    return H, dH, nrep


# ---------------------------------------------------------------------------
# Critical-field estimate for NNN-TFIM
# ---------------------------------------------------------------------------

def sparse_gap_nnn(L: int, h: float, lam: float, tol: float = 1e-8) -> float:
    H, _ = build_nnn_tfim(L, h, lam)
    ev = spla.eigsh(H, k=2, which="SA", tol=tol, return_eigenvectors=False, ncv=30)
    ev = np.sort(ev)
    return float(ev[1] - ev[0])


def _gap_from_components(Hzz: sp.csr_matrix, X: sp.csr_matrix, h: float,
                         tol: float = 1e-7) -> float:
    H = (Hzz - h * X).tocsr()
    dim = H.shape[0]
    ev = spla.eigsh(H, k=2, which="SA", tol=tol, return_eigenvectors=False,
                    ncv=min(dim - 1, 50))
    ev = np.sort(ev)
    return float(ev[1] - ev[0])


def estimate_hc_prg_sector(L: int, lam: float, h_min: float = 0.8,
                           h_max: float = 1.8) -> float:
    """Phenomenological RG using the response sector gap.

    This is a fast, symmetry-reduced estimate useful for L=16,18 exploratory
    runs.  It should be reported as a sector-PRG field if used in final tables.
    """
    if L < 6:
        raise ValueError("PRG estimate uses the pair (L-2,L), so L must be >= 6")
    Hs0, Xs, _ = build_nnn_tfim_sector_components_k0_even(L, lam)
    Hm0, Xm, _ = build_nnn_tfim_sector_components_k0_even(L - 2, lam)

    def f(h: float) -> float:
        return (L - 2) * _gap_from_components(Hm0, Xm, h) - L * _gap_from_components(Hs0, Xs, h)

    grid = np.linspace(h_min, h_max, 21)
    values = [f(float(x)) for x in grid]
    for a, b, fa, fb in zip(grid[:-1], grid[1:], values[:-1], values[1:]):
        if fa == 0:
            return float(a)
        if fa * fb < 0:
            return float(brentq(f, float(a), float(b), xtol=1e-5, rtol=1e-5, maxiter=50))
    return float(grid[int(np.argmin(np.abs(values)))])


def estimate_hc_prg(L: int, lam: float, h_min: float = 0.8, h_max: float = 1.8) -> float:
    """Phenomenological RG: (L-2) Delta_{L-2} = L Delta_L."""
    if L < 6:
        raise ValueError("PRG estimate uses the pair (L-2,L), so L must be >= 6")

    Hs0, Xs = build_nnn_tfim_components(L, lam)
    Hm0, Xm = build_nnn_tfim_components(L - 2, lam)

    def f(h: float) -> float:
        return (L - 2) * _gap_from_components(Hm0, Xm, h) - L * _gap_from_components(Hs0, Xs, h)

    grid = np.linspace(h_min, h_max, 21)
    values = [f(float(x)) for x in grid]
    for a, b, fa, fb in zip(grid[:-1], grid[1:], values[:-1], values[1:]):
        if fa == 0:
            return float(a)
        if fa * fb < 0:
            lo, hi = float(a), float(b)
            flo, _ = float(fa), float(fb)
            for _ in range(30):
                mid = 0.5 * (lo + hi)
                fmid = float(f(mid))
                if abs(hi - lo) < 1e-5:
                    return mid
                if flo * fmid <= 0:
                    hi, _ = mid, fmid
                else:
                    lo, flo = mid, fmid
            return 0.5 * (lo + hi)
    return float(grid[int(np.argmin(np.abs(values)))])


def potts_ladder_prediction() -> float:
    from mpmath import mp, zeta, mpf
    mp.dps = 40
    lamD = lambda s: (1 - mpf(2) ** (-s)) * zeta(s)
    p = mpf(12) / 5
    return float(lamD(2 * p) / lamD(p) ** 2)


def exact_tfim_critical_result(L: int) -> dict:
    """Exact critical TFIM concentration in the NS sector at h=1."""
    KF = (2.0 / 3.0) * (L * L + L - 3.0) / (L * (L - 1.0))
    return {
        "KF": float(KF),
        "KF_half": math.nan,
        "P2": math.nan,
        "P4": math.nan,
        "gap": math.nan,
        "solve_res": math.nan,
        "n_levels": 0,
        "x": np.asarray([], dtype=float),
    }


# ---------------------------------------------------------------------------
# Drivers and I/O
# ---------------------------------------------------------------------------

def parse_even_or_all_L(Lmin: int, Lmax: int, even_only: bool) -> list[int]:
    vals = list(range(Lmin, Lmax + 1))
    if even_only:
        vals = [L for L in vals if L % 2 == 0]
    return vals


def write_benchmark_row(writer: csv.DictWriter, *, model: str, L: int, dim: int,
                        coupling: float, h: float | None, result: dict,
                        method: str, seconds: float, note: str) -> None:
    writer.writerow({
        "model": model,
        "L": L,
        "dim": dim,
        "lambda_or_g": coupling,
        "h": "" if h is None else f"{h:.12g}",
        "KF": f"{result['KF']:.12g}",
        "KF_half": f"{result.get('KF_half', math.nan):.12g}",
        "P2": f"{result['P2']:.12g}",
        "P4_low": f"{result['P4']:.12g}",
        "Neff": f"{1.0 / result['KF']:.12g}",
        "gap_times_L": f"{result['gap'] * L:.12g}",
        "solve_res": f"{result['solve_res']:.3e}",
        "n_levels": result["n_levels"],
        "method": method,
        "seconds": f"{seconds:.3f}",
        "note": note,
    })


def write_weights(writer: csv.DictWriter, *, model: str, L: int, result: dict,
                  source: str, max_ranks: int) -> None:
    xs = np.asarray(result["x"], dtype=float)
    total = float(result["P2"])
    for rank, x in enumerate(xs[:max_ranks], start=1):
        writer.writerow({
            "model": model,
            "L": L,
            "rank": rank,
            "x": f"{x:.16e}",
            "pi": f"{(x / total):.16e}",
            "source": source,
            "KF_of_distribution": f"{result['KF']:.12g}",
        })


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="potts,nnn", help="comma list: potts,nnn")
    parser.add_argument("--Lmin", type=int, default=6)
    parser.add_argument("--Lmax", type=int, default=12,
                        help="max size for Potts (capped at 12); also the default fallback")
    parser.add_argument("--nnn-Lmax", type=int, default=14,
                        help="max size for the NNN-TFIM control (capped at 14, even sizes)")
    parser.add_argument("--k-low", type=int, default=96)
    parser.add_argument("--tol-eig", type=float, default=1e-9,
                        help="ARPACK tolerance for low-energy eigensolves")
    parser.add_argument("--solve-rtol", type=float, default=1e-9,
                        help="MINRES relative tolerance for the projected P2 solve")
    parser.add_argument("--level-group-tol", type=float, default=1e-7,
                        help="energy tolerance for grouping degenerate states into one level projector")
    parser.add_argument("--ncv-factor", type=int, default=4,
                        help="oversampling factor for ARPACK ncv in low-energy eigensolves")
    parser.add_argument("--outdir", type=Path, default=project_root / "data/reproducibility")
    parser.add_argument("--benchmark-csv", default="interacting_benchmarks.csv")
    parser.add_argument("--weights-csv", default="interacting_weight_distributions.csv")
    parser.add_argument("--weights-L", type=int, default=12)
    parser.add_argument("--max-weight-ranks", type=int, default=80)

    parser.add_argument("--potts-method", choices=["k0", "full"], default="k0")
    parser.add_argument("--potts-g", type=float, default=1.0)
    parser.add_argument("--dense-potts-max", type=int, default=7,
                        help="for --potts-method full, use exact dense diagonalization up to this L")

    parser.add_argument("--nnn-lambda", type=float, default=0.2,
                        help="single NNN-TFIM J2 value, ignored when --nnn-lambdas is set")
    parser.add_argument("--nnn-lambdas", default="0,0.05,0.10,0.20",
                        help="comma-separated J2 scan; default matches the manuscript")
    parser.add_argument("--nnn-method", choices=["sector", "full"], default="sector",
                        help="NNN-TFIM response calculation: symmetry sector or full spin basis")
    parser.add_argument("--nnn-prg-method", choices=["full", "sector"], default="full",
                        help="gap crossing used to estimate h_c(L) when --nnn-h is absent")
    parser.add_argument("--nnn-even-only", action="store_true", default=True)
    parser.add_argument("--nnn-h", type=float, default=None,
                        help="fixed h for all NNN-TFIM sizes; default estimates h_c(L) by PRG")
    parser.add_argument("--nnn-h-table", type=Path, default=None,
                        help="optional CSV with columns lambda_or_g,L,h for precomputed PRG fields")
    args = parser.parse_args()

    if args.Lmax > 14:
        raise ValueError("Global Lmax above 14 is not enabled for the Potts workflow; use --nnn-Lmax with --nnn-method sector for larger NNN-TFIM sizes")
    if args.nnn_method == "full" and args.nnn_Lmax > 14:
        raise ValueError("Full-basis NNN-TFIM runs are capped at L <= 14; use --nnn-method sector for larger sizes")
    if args.nnn_method == "sector" and args.nnn_Lmax > 20:
        raise ValueError("Sector NNN-TFIM runs above L=20 are not enabled by this reproducibility script")
    # Potts L>12 is not part of the manuscript benchmark and is too expensive
    # for the intended reproducibility workflow.  The NNN-TFIM control is run
    # separately through L=20 with --nnn-method sector and the confirmed PRG-field
    # table, then merged with the Potts output in the archived CSV.

    models = {m.strip().lower() for m in args.models.split(",") if m.strip()}
    h_table: dict[tuple[float, int], float] = {}
    if args.nnn_h_table is not None:
        with args.nnn_h_table.open(newline="") as hf:
            for row in csv.DictReader(hf):
                h_table[(float(row["lambda_or_g"]), int(row["L"]))] = float(row["h"])
    args.outdir.mkdir(parents=True, exist_ok=True)
    bench_path = args.outdir / args.benchmark_csv
    weights_path = args.outdir / args.weights_csv

    bench_fields = ["model", "L", "dim", "lambda_or_g", "h", "KF", "KF_half", "P2", "P4_low",
                    "Neff", "gap_times_L", "solve_res", "n_levels", "method", "seconds", "note"]
    weight_fields = ["model", "L", "rank", "x", "pi", "source", "KF_of_distribution"]

    with bench_path.open("w", newline="") as bf, weights_path.open("w", newline="") as wf:
        bench_writer = csv.DictWriter(bf, fieldnames=bench_fields)
        weight_writer = csv.DictWriter(wf, fieldnames=weight_fields)
        bench_writer.writeheader()
        weight_writer.writeheader()

        if "potts" in models:
            if args.Lmax > 12:
                raise ValueError("Potts benchmark is capped at Lmax <= 12 (use --nnn-Lmax with --nnn-method sector for larger NNN-TFIM controls)")
            print(f"Potts ideal single-soft-ladder benchmark: {potts_ladder_prediction():.6f}")
            for L in range(args.Lmin, args.Lmax + 1):
                t0 = time.time()
                if args.potts_method == "full":
                    if L <= args.dense_potts_max:
                        H, dH = build_potts_full(L, args.potts_g)
                        result = dense_level_projector_kf(H, dH, tol_group=args.level_group_tol)
                        dim = 3**L
                        method = "full-dense"
                    else:
                        H, dH = build_potts_full(L, args.potts_g)
                        Hs = sp.csr_matrix(H)
                        dHs = sp.csr_matrix(dH)
                        result = hybrid_level_projector_kf(Hs, dHs, args.k_low, tol_eig=args.tol_eig,
                                                           tol_group=args.level_group_tol,
                                                           rtol_solve=args.solve_rtol,
                                                           ncv_factor=args.ncv_factor)
                        dim = 3**L
                        method = "full-hybrid"
                else:
                    Hs, dHs, dim = build_potts_k0(L, args.potts_g)
                    result = hybrid_level_projector_kf(Hs, dHs, args.k_low, tol_eig=args.tol_eig,
                                                       tol_group=args.level_group_tol,
                                                       rtol_solve=args.solve_rtol,
                                                       ncv_factor=args.ncv_factor)
                    method = "k0-hybrid"
                seconds = time.time() - t0
                write_benchmark_row(bench_writer, model="Potts", L=L, dim=dim,
                                    coupling=args.potts_g, h=None, result=result,
                                    method=method, seconds=seconds,
                                    note="critical self-dual point")
                if L == args.weights_L:
                    write_weights(weight_writer, model="Potts", L=L, result=result,
                                  source=method, max_ranks=args.max_weight_ranks)
                print(f"Potts L={L:2d} dim={dim:>8} K_F={result['KF']:.6f} "
                      f"Neff={1/result['KF']:.3f} gap*L={result['gap']*L:.3f} "
                      f"res={result['solve_res']:.1e} {seconds:.1f}s", flush=True)

        if "nnn" in models or "nnn-tfim" in models:
            if args.nnn_lambdas is None:
                lambdas = [args.nnn_lambda]
            else:
                lambdas = [float(x) for x in args.nnn_lambdas.split(",") if x.strip()]
            Ls = parse_even_or_all_L(args.Lmin, args.nnn_Lmax, args.nnn_even_only)
            for lam in lambdas:
                for L in Ls:
                    t0 = time.time()
                    if abs(lam) < 1e-14 and args.nnn_h is None:
                        h = 1.0
                        result = exact_tfim_critical_result(L)
                        seconds = time.time() - t0
                        method = "exact-TFIM"
                        note = "exact critical TFIM NS-sector formula"
                    else:
                        if args.nnn_h is not None:
                            h = args.nnn_h
                            prg_note = "fixed-h"
                        elif (lam, L) in h_table:
                            h = h_table[(lam, L)]
                            prg_note = "tabulated full-PRG"
                        elif args.nnn_prg_method == "sector":
                            h = estimate_hc_prg_sector(L, lam)
                            prg_note = "sector-PRG"
                        else:
                            h = estimate_hc_prg(L, lam)
                            prg_note = "full-PRG"
                        if args.nnn_method == "sector":
                            Hs, dHs, dim_nnn = build_nnn_tfim_sector_k0_even(L, h, lam)
                            method = "PRG-sector-hybrid"
                        else:
                            Hs, dHs = build_nnn_tfim(L, h, lam)
                            dim_nnn = 1 << L
                            method = "PRG-hybrid"
                        result = hybrid_level_projector_kf(Hs, dHs, args.k_low, tol_eig=args.tol_eig,
                                                           tol_group=args.level_group_tol,
                                                           rtol_solve=args.solve_rtol,
                                                           ncv_factor=args.ncv_factor)
                        seconds = time.time() - t0
                        note = f"finite-size nonintegrable Ising-line control; {prg_note}"
                    write_benchmark_row(bench_writer, model="NNN-TFIM", L=L, dim=(1 << L) if abs(lam) < 1e-14 and args.nnn_h is None else dim_nnn,
                                        coupling=lam, h=h, result=result,
                                        method=method, seconds=seconds,
                                        note=note)
                    if L == args.weights_L and result["n_levels"]:
                        write_weights(weight_writer, model="NNN-TFIM", L=L, result=result,
                                      source=method, max_ranks=args.max_weight_ranks)
                    gapL = result['gap'] * L if np.isfinite(result['gap']) else math.nan
                    print(f"NNN-TFIM L={L:2d} J2={lam:g} h={h:.8f} "
                          f"K_F={result['KF']:.6f} Neff={1/result['KF']:.3f} "
                          f"gap*L={gapL:.3f} res={result['solve_res']:.1e} "
                          f"{seconds:.1f}s", flush=True)

    print(f"wrote {bench_path}")
    print(f"wrote {weights_path}")


if __name__ == "__main__":
    main()
