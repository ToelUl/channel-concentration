# Conditional channel-refinement bounds

This directory supplies the small, public mathematical check for the R3
refinement material in the manuscript. It is separate from the immutable
numerical baseline and the seven-figure presentation companion.

## Run the check

From the repository root, with Python 3.12 or newer:

```sh
python -B r3_support/verify_refinement_budgets.py
```

The script uses only the Python standard library. It recomputes the Ising and
Potts thermal-family intervals using outward-rounded Decimal operations and
analytic tails, then compares the full result with
[`expected_bound_enclosures.json`](expected_bound_enclosures.json). It also
checks exact rational refinement examples, an independent Ising character
count, character coefficients, cutoff and precision consistency, and rejection
outside the implemented tail domain. It neither runs lattice calculations nor
edits the manuscript or baseline. To save a regenerated receipt separately,
pass `--output PATH`; the reviewed receipt cannot be overwritten through this
option.

## Finite-size argument

Let nonnegative fine-channel projector masses sum to one. For a disjoint group
`N`, write `q_N` for its total mass and `m_N` for its positive-weight channel
count. Cauchy–Schwarz gives `sum_a pi_(N,a)^2 >= q_N^2/m_N`; hence the
grouped-minus-fine concentration is between zero and
`sum_N (1 - 1/m_N) q_N^2`. Equality in the upper bound occurs when positive
weights within each group are equal. Zero-mass groups contribute zero and do
not need a positive-channel count.

For a reference distribution `pi_N*`, choose at most `M_N` *actual* fine
channels in each group, with each positive integer `M_N` fixed independently
of system size. Let `e_N` be the omitted mass, `t_N = q_N - e_N`,
`delta_grp = sum_N |q_N - pi_N*|`, and `delta_out = sum_N e_N`. Then

```text
K_fine >= sum_N t_N^2 / M_N
|sum_N (t_N^2 - (pi_N*)^2) / M_N| <= 2(delta_grp + delta_out)
K_fine <= sum_N q_N^2 <= K_star + 2 delta_grp
B_M = sum_N (1 - 1/M_N) (pi_N*)^2
```

Therefore `K_star - B_M - 2(delta_grp + delta_out) <= K_fine <=
K_star + 2 delta_grp`. If both errors tend to zero, every subsequential
limit lies in `[K_star - B_M, K_star]`. No uniqueness or convergence rate
follows. The finite examples in the script check arithmetic and boundary
cases; the proof requires the normalized projector partition and the stated
support selection.

## What the manuscript uses

| Manuscript statement | Public check | Scope |
| --- | --- | --- |
| Finite-size refinement inequality, Eq. `resolution-finite-bound` | Exact rational examples and equality case | The proof is Cauchy–Schwarz for exact projector masses of one normalized response vector. Finite examples test the implementation of the formula; they do not replace the proof. |
| Reference inequality, Eqs. `resolution-error-definitions` and `resolution-reference-bound` | Exact rational examples with zero and nonzero grouped matching and outside-support errors | The subsets must contain actual finite-size fine channels; each budget `M_N` is a fixed positive integer. |
| Conditional subsequential-limit band, Eq. `resolution-limit-band` | Follows algebraically from the finite-size inequality if both errors tend to zero | This repository does not establish that either error tends to zero for the archived lattice sequences. |
| Thermal budgets, Eq. `thermal-budget-values` | Recomputed reviewed intervals | `B_Ising < 1.68e-4` and `B_Potts < 4.04e-5` are bounds for the CFT reference families. Their use for a lattice observable additionally requires grouped matching and the stated finite-size projector-support condition. |
| Analytic tails, Eq. `thermal-budget-tails` | Cutoff and precision checks; invalid-domain rejection | The implemented integral-tail argument is restricted to `0 < Delta <= 1`, which covers the two thermal dimensions checked here. |
| Weaker Potts alternative, Eq. `potts-leading-group-budget` | `all_n_ge_1_squared` in the receipt | This avoids the excited-group family-multiplicity assumption but still needs a leading group that remains unsplit and grouped matching. |

The output contains complete interval endpoints at `N=200,400` and 60/90
decimal digits. Its status certifies the stated arithmetic checks, not a
thermodynamic limit, a finite-size convergence rate, or universal fine-channel
amplitude. The response-vector normalization, group labels, support subsets,
and tail must be matched separately in any lattice application.

## Origin and identity

The reviewed local R3 verification receipt had SHA-256
`baaac55e3f24e06ac72ea8ca44e0ee7741d86d9d7332aa7a25cf354e847b5023`;
the committed expected JSON is byte-identical. The public script is a
no-write adaptation of the reviewed standard-library checker, whose original
SHA-256 was
`78d8a9f17eb82c8348ddc5bc109352219b0a926acb32585911237d0a8fcc3685`.
No private review correspondence or private manuscript source is included.
