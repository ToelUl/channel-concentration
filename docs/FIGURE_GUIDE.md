# Figure guide: paper result to public computation and evidence

This guide is the human route through Figures 1–6 and S1. The [machine figure map](../companion/FIGURE_MAP.json) binds selectors, renderers, filenames, direct inputs, and the same code routes returned by `companion/run.py describe`; the [evidence guide](EVIDENCE_MAP.md) explains evidence classes; the [companion guide](../companion/README.md) explains the commands. The immutable numerical authority is `baseline-2026-09-09-rc1`. R6a denotes the author's collaborator-consensus manuscript source. Its labels below are human navigation hints, not a claim that this public repository contains that source or its final version.

Run `python -B companion/run.py verify` before using the companion. The publication command for an individual figure is `python -B companion/run.py render --fig <selector>` with a fresh output directory. Integrity, scientific-contract, and exact artwork checks answer different questions; see [verification](VERIFICATION.md). No rendering command performs an interacting eigensolve or a new fit.

## Figure 1 — TFIM–XX response and channel concentration {#figure-1}

**Quick trace**

| Field | Value |
| --- | --- |
| Identity | `1`, `tfim_critical_concentration`, `fig:twothirds` |
| Scientific role | Compare total response, infrared carrier ladders, and exact finite-size concentration for TFIM and XX. |
| Computation class | `analytic-closed-form` |
| Panels | (a) total-response scaling; (b) one and two soft ladders; (c) exact finite-size concentration. |
| Direct renderer inputs | None; the renderer evaluates analytic formulas and free-fermion sums. |
| Source code | [Exact-coordinate calculation and publication renderer](../companion/scripts/plotting/generate_figures.py#L506) |
| Reproduce | `python -B companion/run.py render --fig 1` |

**Code route**

1. Scientific computation: [`plot_fig1_tfim_critical_concentration`](../companion/scripts/plotting/generate_figures.py#L506) evaluates the closed finite-size TFIM/XX moments and limiting ladder weights directly.
2. Data transformation: [`get_params`](../companion/scripts/plotting/generate_figures.py#L367) binds the publication size grid; there is no archived numerical input for this figure.
3. Publication renderer: the same frozen [`plot_fig1_tfim_critical_concentration`](../companion/scripts/plotting/generate_figures.py#L506) function assembles and draws all three panels.

**Technical trace**

- Manuscript anchors: `sec:tfim`, `sec:tfim:twothirds`, `sec:xy:xx-theorem`, `fig:twothirds`; the exact NS and XX half-size derivations are in `app:tfim-scaling` and `app:xx-pairing-theorem`.
- Renderer and parameters: `plot_fig1_tfim_critical_concentration`; publication sizes `L=16,24,32,48,64,96,128,192,256,384,512,768,1024` plus analytic ladder display. See `get_params('publication')` in the frozen renderer for the exact grid.
- Upstream route: closed-form TFIM/XX finite-size formulas and free-fermion mode sums; no archived interacting table feeds this figure. The packaged historical `xx_pairing_theorem_checks.csv` is a related check, not a direct plot input.
- Verification and scope: companion identity/artwork checks bind the renderer and PDFs; analytic artist checks bind the complete panel-(b) soft-ladder bar heights to their limiting formulas. Bounded scientific contracts compare direct sums, closed forms, and the distribution-level half-size identity. Those numerical checks test selected sizes and do not replace the theorem's assumptions.

## Figure 2 — TFIM scaling and conditional ladder envelope {#figure-2}

**Quick trace**

| Field | Value |
| --- | --- |
| Identity | `2`, `scaling_and_envelope`, `fig:collapse` |
| Scientific role | Show finite-size collapse toward the parameter-free NS scaling function and the ideal odd-ladder envelope. |
| Computation class | `analytic-free-fermion` |
| Panels | (a) TFIM scaling collapse; (b) envelope versus exponent. |
| Direct renderer inputs | None. |
| Source code | [`Phi` and `KFcrit_p`](../companion/scripts/plotting/generate_figures.py#L246), [finite-size channel weights](../companion/scripts/plotting/generate_figures.py#L228), [publication renderer](../companion/scripts/plotting/generate_figures.py#L597) |
| Reproduce | `python -B companion/run.py render --fig 2` |

**Code route**

1. Scientific computation: [`Phi`](../companion/scripts/plotting/generate_figures.py#L246) evaluates the TFIM scaling function and [`KFcrit_p`](../companion/scripts/plotting/generate_figures.py#L270) evaluates the odd-ladder envelope.
2. Data transformation: [`channel_weights`](../companion/scripts/plotting/generate_figures.py#L228) turns finite-size Bogoliubov-angle gradients into the plotted marker values.
3. Publication renderer: [`plot_fig2_scaling_and_envelope`](../companion/scripts/plotting/generate_figures.py#L597) assembles the collapse and envelope panels.

**Technical trace**

- Manuscript anchors: `sec:tfim:scaling`, `eq:Phi`, `sec:tfim:envelope`, `eq:envelope`, `fig:collapse`; the conditional RG discussion is under `app:rg-envelope`.
- Renderer and parameters: `plot_fig2_scaling_and_envelope`; publication `L=512,2048,8192,32768`, `mu` samples from `-6` to `6`, 401-point curve grid, and 50,000-term `Phi` helper. The envelope panel uses its own exponent grid.
- Upstream route: exact lattice free-fermion weights and analytic odd-ladder sums; no external plot input. The exact endpoint is `Phi(0)=2/3`. A finite `Phi(0,nmax=50000)` value is a truncated numerical helper, not the exact endpoint oracle.
- Verification and scope: the scientific-contract verifier checks selected lattice-to-scaling values, a registered absolute error ceiling at `L=2048`, and finite odd-ladder sums with explicit truncation-tail bounds. Analytic artist checks bind all four plotted finite-size marker series to separate NS-mode evaluations. The ceiling is a guard on the specified grid, not a universal error estimate. The envelope applies to its stated single-ladder premises; the plot does not itself establish that every interacting model follows it.

## Figure 3 — Lifshitz directional selectivity {#figure-3}

**Quick trace**

| Field | Value |
| --- | --- |
| Identity | `3`, `lifshitz_anisotropy_scaling`, `fig:lifshitz` |
| Scientific role | Separate anisotropy and field directions near the Lifshitz point and display their distinct scaling functions. |
| Computation class | `analytic-free-fermion` |
| Panels | (a) two tangent directions at fixed size; (b) directional scaling functions. |
| Direct renderer inputs | None. |
| Source code | [`KF_point`, `Phi`, and `Psi`](../companion/scripts/plotting/generate_figures.py#L238), [publication renderer](../companion/scripts/plotting/generate_figures.py#L683) |
| Reproduce | `python -B companion/run.py render --fig 3` |

**Code route**

1. Scientific computation: [`KF_point`](../companion/scripts/plotting/generate_figures.py#L238) evaluates the finite-size mode sums, while [`Phi`](../companion/scripts/plotting/generate_figures.py#L246) and [`Psi`](../companion/scripts/plotting/generate_figures.py#L258) evaluate the two scaling functions.
2. Data transformation: [`get_params`](../companion/scripts/plotting/generate_figures.py#L367) binds the fixed-size and scaling-window grids; no archived plot table is read.
3. Publication renderer: [`plot_fig3_lifshitz_anisotropy_scaling`](../companion/scripts/plotting/generate_figures.py#L683) assembles the directional and scaling panels.

**Technical trace**

- Manuscript anchors: `sec:lifshitz`, `sec:lifshitz:scaling`, `eq:lifshitz-scaling`, `eq:Psi`, `sec:lifshitz:order`, `fig:lifshitz`.
- Renderer and parameters: `plot_fig3_lifshitz_anisotropy_scaling`; publication fixed `L=65536`, scaling sizes `4096,16384,65536`, nine displayed `w` values, and a 320-point geometric `w` curve. See frozen `get_params` for gamma grid and exact cutoffs.
- Upstream route: XY free-fermion mode weights and the `Phi(2w)` / `Psi(w)` scaling expressions; no archived table is read to draw the figure.
- Verification and scope: the contract checks selected lattice-to-scaling points, separate finite-grid anisotropy and field error ceilings, `Psi(0)=lambda_D(12)/lambda_D(6)^2`, and the field-direction singular endpoint. Analytic artist checks bind all six plotted finite-size marker series to separate NS-mode evaluations. At exactly `(h,gamma)=(1,0)` the field-direction `P2` vanishes, so normalized concentration is undefined; the shown limit is punctured. Moving-path asymptotics remain derivations outside routine CI.

## Figure 4 — Interacting finite-size comparisons {#figure-4}

**Quick trace**

| Field | Value |
| --- | --- |
| Identity | `4`, `interacting_benchmarks`, `fig:interacting-benchmarks` |
| Scientific role | Compare accessible-size Potts and NNN-TFIM diagnostics with analytic reference information. |
| Computation class | `archived-interacting-hybrid` |
| Panels | (a) Potts finite-size values and fixed references; (b) NNN-TFIM versus same-size exact TFIM. |
| Direct renderer inputs | `interacting_benchmarks.csv`, `potts_outcome_aware_fss.csv`, `potts_theory_guided_7over5_receipt.json`, `envelope_predictions_table.csv` in `baseline/data/figure-inputs/`. |
| Source code | [Potts producer](../baseline/software/src/cc_repro/_resources/original/scripts/simulation/simulate_interacting_benchmarks.py#L881), [NNN producer](../baseline/software/src/cc_repro/_resources/original/scripts/simulation/reproduce_nnn_tfim_expensive.py#L591), [archived replay](../baseline/tools/replay_current.py#L12), [publication renderer](../companion/scripts/plotting/generate_figures.py#L772) |
| Reproduce | `python -B companion/run.py render --fig 4` |

**Code route**

1. Scientific computation: the preserved [Potts campaign](../baseline/software/src/cc_repro/_resources/original/scripts/simulation/simulate_interacting_benchmarks.py#L881) and [NNN publication campaign](../baseline/software/src/cc_repro/_resources/original/scripts/simulation/reproduce_nnn_tfim_expensive.py#L591) are the producer routes behind the archive. They may perform eigensolves and are not routine figure commands.
2. Data transformation and archived input: [`regenerate_potts_fss.py`](../baseline/software/src/cc_repro/_resources/original/scripts/cleanroom/regenerate_potts_fss.py#L72), [`derive_potts_theory_guided_7over5.py`](../baseline/software/src/cc_repro/_resources/original/scripts/analysis/derive_potts_theory_guided_7over5.py#L254), and [`compute_envelope_table`](../baseline/software/src/cc_repro/_resources/original/scripts/reproducibility/reproduce_numerics.py#L322) create the frozen inputs. [`replay_current.py`](../baseline/tools/replay_current.py#L12) restores archived runs and checks selected postprocessors without a new eigensolve.
3. Publication renderer: [`plot_fig4_interacting_benchmarks`](../companion/scripts/plotting/generate_figures.py#L772) reads the four frozen inputs and existing coefficients; `render --fig 4` neither runs the campaigns nor refits the data.

**Technical trace**

- Manuscript anchors: `sec:interacting-benchmarks`, `eq:level-projector-benchmark`, `fig:interacting-benchmarks`; the conditional Potts comparison is under `eq:cft-grouped-matching` and `eq:potts-KF-correction-hierarchy`.
- Renderer and parameters: `plot_fig4_interacting_benchmarks`; Potts fixed sizes `L=6–14`, NNN `J2=0.05,0.1,0.2` at the archived sizes. The Potts horizontal coordinate uses the receipt's `7/5` exponent; the fixed label is valid only when that contract matches. The NNN panel derives its exact TFIM reference at the same size.
- Potts provenance: production diagonalizes the full translation-invariant `k=0` block, without an explicit production `q=0` projection. Its finite-size ground state and thermal response have `q=0` support, consistent with symmetry/Perron–Frobenius reasoning and the related `potts_charge_sector_checks.csv`. The legacy L≤12 source header is historical; the retained-eigenpair production route uses that builder through `L=14`.
- Potts observable semantics: `r_a=||Pi_a chi||^2` is exact projector response mass; `x_a=||Pi_a V|0>||^2 / mean_gap_a^2` is a mean-gap approximation; `K_F^proj=sum_a r_a^2/P2^2` is the exact target. The plotted scalar is the historical retained mean-gap numerator with independently solved projected-resolvent `P2` and its archived tail treatment. Do not substitute the later exact-projector enclosure midpoint into the frozen plot.
- Related Potts records: fixed-grid `potts_outcome_aware_fss.csv` feeds Figure 4(a); separate L12–14 spectral-tail records, including `projector-response-enclosures.json`, provide conditional same-response qualification. `potts_theory_guided_7over5_fit_summary.csv`, `potts_scaled_P2_7over5.csv`, and `potts_outcome_aware_fit_audit.csv` document correction diagnostics. Evidence by size: L6 complete-sector; L7–11 retained-count diagnostic; L12–14 also have conditional exact-projector enclosures. The `L^-7/5` axis is an accessible-size diagnostic motivated by `P2_UV/P2_sing`, not a unique asymptotic correction theorem for these fine-level points.
- NNN provenance: publication PRG uses `reproduce_nnn_tfim_expensive.py :: root_task`, the `k=0` odd–even global-spin-flip scaled-gap crossing. It is distinct from exploratory PRG helpers. The NNN points use finite-size pseudocritical `h_cross(L,J2)`; exact TFIM reference uses `h_c=1` at the same L, not the same finite-size prescription. NNN values remain retained mean-gap level-projector diagnostics with independent `P2`; they have no Potts-style L12–14 same-response enclosure.
- Verification and scope: input hashes and the Figure 4 artist-coordinate check bind archived values to the plot. Bounded checks cover Potts charge support, a nonzero-J2 parity-sector matrix comparison, PRG/response thresholds, and the exponent/label guard. These do not rerun the large campaigns or prove thermodynamic convergence.

## Figure 5 — Ranked response distributions {#figure-5}

**Quick trace**

| Field | Value |
| --- | --- |
| Identity | `5`, `ranked_response_distributions`, `fig:potts-weight-comparators` |
| Scientific role | Compare what retained channel ranks show in Potts and NNN-TFIM while exposing their different completeness limits. |
| Computation class | `archived-interacting-distribution` |
| Panels | (a) Potts retained ranks 1–15 with inset 2–15; (b) NNN ranks and a visual exact TFIM L20 overlay. |
| Direct renderer inputs | `potts_L14_certified_ranked_weights.csv`, `nnn_ranked_distribution_convergence.csv`, `nnn_ranked_distribution_convergence_receipt.json` in `baseline/data/figure-inputs/`; `companion/inputs/cft/cft_kf_results.json` is a direct evidence projection. |
| Source code | [Potts producer](../baseline/software/src/cc_repro/_resources/original/scripts/simulation/simulate_interacting_benchmarks.py#L881), [NNN producer](../baseline/software/src/cc_repro/_resources/original/scripts/simulation/reproduce_nnn_tfim_expensive.py#L591), [ranked postprocessors](../baseline/software/src/cc_repro/_resources/original/scripts/analysis/derive_potts_certified_ranked_weights.py#L65), [publication renderer](../companion/scripts/plotting/generate_figures.py#L945) |
| Reproduce | `python -B companion/run.py render --fig 5` |

**Code route**

1. Scientific computation: the preserved [Potts retained-eigenpair campaign](../baseline/software/src/cc_repro/_resources/original/scripts/simulation/simulate_interacting_benchmarks.py#L881) and [NNN publication campaign](../baseline/software/src/cc_repro/_resources/original/scripts/simulation/reproduce_nnn_tfim_expensive.py#L591) are historical producer routes and may perform eigensolves.
2. Data transformation and archived input: [`derive_potts_certified_ranked_weights.py`](../baseline/software/src/cc_repro/_resources/original/scripts/analysis/derive_potts_certified_ranked_weights.py#L65) and [`derive_nnn_ranked_distribution_convergence.py`](../baseline/software/src/cc_repro/_resources/original/scripts/analysis/derive_nnn_ranked_distribution_convergence.py#L221) create the plotted ranked tables. [`replay_current.py`](../baseline/tools/replay_current.py#L12) checks those postprocessors from archived inputs without a new eigensolve. [`companion/run.py verify`](../companion/run.py#L120) validates the lossless CFT evidence projection; it does not perform a new lattice calculation.
3. Publication renderer: [`plot_fig5_distribution_comparisons`](../companion/scripts/plotting/generate_figures.py#L945) reads the frozen tables and verified projection and renders the two ranked-distribution panels.

**Technical trace**

- Manuscript anchors: `sec:interacting-benchmarks`, `fig:potts-weight-comparators`, and the resolution discussion under `sec:discussion:interacting`.
- Renderer and parameters: `plot_fig5_distribution_comparisons`; Potts L14 displays 15 retained ranks, NNN J2=0.2 overlays L6,10,14,20, and exact TFIM L20 supplies the visual reference. The quantitative ranked-TV postprocessor instead compares each NNN size with same-size exact TFIM.
- Potts provenance and rank semantics: 109 retained groups, 18 strictly positive lower bounds, and 15 displayed retained ranks at L14. Retained ordering is protected for ranks 1–15; protection against *any omitted channel* is established only for ranks 1–10. The frozen filename `certified_ranked_weights` does not certify global full-spectrum ranks 11–15. The bars use historical `x_a/P2`; conditional `r_a/P2` intervals support their displayed precision/order without replacing the bars. A related enclosure gives an omitted exact-probability upper bound of about `1.051e-6` under its premises.
- NNN provenance and tail semantics: the postprocessor selects the richest sealed checkpoint matching the released scalar within tolerance; this selects provenance, not a new convergence proof. `n_low_energy_eigenpairs` is requested, while nominal/returned counts may be sector-capped. Related count sidecars distinguish requested, nominal, solver-returned, guard-used, and retained-group counts. The unresolved `1-sum_R x_r/P2` is mean-gap bookkeeping mass, not a certified omitted exact-response probability. Missing retained ranks are plotted as zero padding, not asserted physical zeros.
- Verification and scope: the Figure 5 artist check binds plotted bars and reference coordinates to archived inputs. Semantic checks enforce the Potts top-ten omitted-channel boundary and NNN record limits. The CFT projection is bound to its source decimal strings; its presence is not a proof of lattice–CFT matching.

## Figure 6 — XY directional profiles {#figure-6}

**Quick trace**

| Field | Value |
| --- | --- |
| Identity | `6`, `xy_directional_profiles`, `fig:xy-directional-profiles` |
| Scientific role | Show how concentration depends on the probe tangent in a gapped XY point and near the Lifshitz region. |
| Computation class | `analytic-free-fermion` |
| Panels | (a) gapped XY polar profile; (b) regulated near-Lifshitz polar profile. |
| Direct renderer inputs | None. |
| Source code | [`KF_point` and `channel_weights`](../companion/scripts/plotting/generate_figures.py#L228), [publication renderer](../companion/scripts/plotting/generate_figures.py#L1141) |
| Reproduce | `python -B companion/run.py render --fig 6` |

**Code route**

1. Scientific computation: [`KF_point`](../companion/scripts/plotting/generate_figures.py#L238) evaluates the XY concentration for each tangent direction from exact mode sums.
2. Data transformation: [`channel_weights`](../companion/scripts/plotting/generate_figures.py#L228) converts each tangent into channel weights before the renderer normalizes and mirrors the polar curve.
3. Publication renderer: [`plot_fig6_xy_directional_profiles`](../companion/scripts/plotting/generate_figures.py#L1141) draws the gapped and regulated near-Lifshitz profiles.

**Technical trace**

- Manuscript anchors: `sec:directional`, `eq:KF-directional`, `eq:tangent-angle-varphi`, `fig:xy-directional-profiles` in the main appendix.
- Renderer and parameters: `plot_fig6_xy_directional_profiles`; publication L2000, gapped point `(h,gamma)=(0.8,0.5)`, near-Lifshitz regularization `s=0.05`, and 241 tangent samples from 0 to pi.
- Upstream route: XY free-fermion directional weights evaluated by the renderer. Related supporting record `baseline/data/figure-inputs/xy_directional_scan.csv` uses the same gapped publication point and grid but is not a direct render input.
- Verification and scope: the gapped full curve is compared with the archived scan, while the near-Lifshitz polar curve is bound to a separate NS-mode evaluation. Independent checks of scale, sign, and pi-periodicity act on the underlying physics function; mirroring a rendered curve alone is not an independent invariant check.

## Figure S1 — Weak one-sided quench extraction {#figure-s1}

**Quick trace**

| Field | Value |
| --- | --- |
| Identity | `S1`, `weak_quench_extraction`, `fig:quench`; standalone supplement calls it Figure 1. |
| Scientific role | Connect excitation counting and normalized pair weights to the ground-state channel concentration in a weak one-sided quench. |
| Computation class | `analytic-free-fermion-quench` |
| Panels | (a) normalized excitation weights; (b) counting ratio versus amplitude. |
| Direct renderer inputs | None. |
| Source code | [Exact quench probabilities and counting ratio](../companion/scripts/plotting/generate_figures.py#L282), [publication renderer](../companion/scripts/plotting/generate_figures.py#L1275) |
| Reproduce | `python -B companion/run.py render --fig S1` |

**Code route**

1. Scientific computation: [`weak_quench_probabilities_h`](../companion/scripts/plotting/generate_figures.py#L282) evaluates exact BdG pair probabilities and [`R_from_probabilities`](../companion/scripts/plotting/generate_figures.py#L295) evaluates the counting ratio.
2. Data transformation: [`channel_weights`](../companion/scripts/plotting/generate_figures.py#L228) forms the normalized quadratic reference distribution; no archived plot table is read.
3. Publication renderer: [`plot_figS1_weak_quench_extraction`](../companion/scripts/plotting/generate_figures.py#L1275) assembles the normalized-weight and finite-amplitude panels.

**Technical trace**

- Manuscript anchors: `supp:sec:operational-access`, `supp:eq:quench-KF`, `app:weak-quench`, `app:weak-quench-budget`, `fig:quench`.
- Renderer and parameters: `plot_figS1_weak_quench_extraction`; publication L256, initial `h0=1`, `gamma=1`, displayed delta values `0.0005,0.0015,0.003`, 48-point delta grid `0.0002–0.0035`, and first 100 displayed ranks.
- Upstream route: exact BdG pair probabilities and free-fermion counting identities; no table is read to draw S1. Related supporting records: `baseline/data/figure-inputs/weak_quench_delta_budget.csv` and `weak_quench_fixed_u_feasibility.csv` document finite-amplitude and fixed-u limits.
- Verification and scope: bounded checks cover `mean(N)-Var(N)=sum_k p_k^2`, normalized distribution convergence, and the critical-TFIM quadratic drift using independently evaluated closed `P2`, `P4`, and `P6` moments. Analytic artist checks bind the full plotted normalized-weight series for the quadratic prediction and three amplitudes to separate mode formulas. The renderer currently evaluates an algebraically equivalent difference of moments; the frozen renderer remains unchanged. Finite delta and finite size retain the documented budget limits.

## Where to go next

- [Companion commands and output receipts](../companion/README.md)
- [Evidence classes and current versus historical records](EVIDENCE_MAP.md)
- [Baseline reproduction procedure](../baseline/docs/REPRODUCE.md) and [known limitations](../baseline/docs/KNOWN_LIMITATIONS.md)
- [Verification scope](VERIFICATION.md) and [approved artwork identities](../companion/ARTWORK.json)
