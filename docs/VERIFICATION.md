# Verification summary

This English summary describes the recorded checks for numerical release `baseline-2026-09-09-rc1`. It does not replace or modify the original verification receipts. The public release and its hosted CI status were checked on 2026-09-10.

## Three verification scopes

| Scope | Public command | What it establishes |
| --- | --- | --- |
| Integrity | `python -B baseline/tools/verify_release.py` and `python -B companion/run.py verify` | Frozen file, input, renderer, figure-map, and projection identities. It does not independently recalculate the science. |
| Scientific contracts | `python -B tools/verify_scientific_contracts.py` | Selected exact formulas, bounded fresh small-sector checks, archived PRG/response thresholds, and rank semantics. It does not rerun large campaigns or prove full manuscript claims. |
| R3 conditional theory check | `python -B r3_support/verify_refinement_budgets.py` | Recomputed outward intervals, character and tail checks, and exact rational finite-refinement examples. Lattice grouped matching and fine-channel support are unverified premises. |
| Approved artwork identity | `python -B companion/run.py verify-artwork` after complete publication rendering in the author-approved environment | Exact match of all seven PDFs to the author-approved S2 artwork hashes. It is not a new human review or final venue approval. |
| Hosted artwork contract | `python -B companion/run.py verify-hosted-artwork` after complete publication rendering | Six PDFs match their approved hashes exactly. S1 must match its frozen plot-data structure and x coordinates, all y coordinates within a documented narrow relative tolerance, and its approved-render PNG hash. The result explicitly distinguishes `EXACT_7_OF_7` from `PORTABLE_S1_CHECK`; the latter is not seven-PDF exact reproduction or a new artwork approval. |

Full rendering also exports plot data and checks sixteen interacting coordinates/bars and eleven selected analytic coordinate contracts. A one-figure render checks only its relevant coordinates and never passes the seven-PDF artwork check. The `exact fast` route in the numerical release shows that a bounded analytic computation route executes; it is not a complete independent proof of every manuscript analytic identity. The scientific-contract command makes selected contracts active, with the stated finite-size scope.

## Clean installation and bounded tests

The local packaging verification used new environments and installed the fixed dependencies without changing the original producer environments. Wheels and source distributions for all three versions installed successfully. Detached tests loaded the installed packages from `site-packages`.

| Version | Passing tests in its recorded suite |
|---|---:|
| `0.5.0.dev0` | 45 |
| `0.5.1.dev0` | 58 |
| `0.5.2.dev0` | 69 |

The suites overlap. Their counts must not be summed and described as independent scientific calculations.

## Recorded numerical checks

Five current postprocessing routes passed: Potts finite-size scaling, Potts ranked weights, NNN ranked weights, the Potts 7/5 analysis, and conditional projector-response enclosures. For the first four routes, six CSV outputs matched the baseline byte for byte. Enclosure checks compared the numerical structure and stated premises. These checks used the archived inputs without rerunning large eigensolves.

Three additional small fresh routes also succeeded: the fast exact route, Potts at L = 6, and NNN at L = 6 with J2 = 0.2. Dependency consistency checks passed.

The historical packaging report separately verified an earlier local index of 1,123 files. That count refers to a different local inventory and must not be used as the count of files in the public distribution.

## Public projections and integrity

Four nonessential derived receipts were distributed as explicit public projections to remove local paths or host identifiers. The projections identify the original hashes and changed fields. Original committed numerical inputs, checkpoints, and source code were preserved.

The baseline manifest and checksum records bind the distributed payload. Run the integrity checker before and after local use. Use new workspaces for replay and fresh calculations.

## Hosted CI

The [baseline integrity and bounded regressions workflow](https://github.com/ToelUl/channel-concentration/actions/runs/34334051364) completed successfully for commit `6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da`. It verifies baseline bytes, installs each selected wheel with fixed dependencies, runs detached small tests, and checks that the baseline remains unchanged.

Hosted CI does not reproduce the original platform/BLAS identity, perform all strict current-result routes, rerun large campaigns, or verify a final manuscript or publication artwork.

## Evidence and limits

The recorded machine-readable local checks are in [CLEAN_INSTALL_AND_REPLAY.json](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/verification/CLEAN_INSTALL_AND_REPLAY.json) and [PAYLOAD_AUDIT.json](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/verification/PAYLOAD_AUDIT.json). Interpret results with the [known limitations](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/docs/KNOWN_LIMITATIONS.md).

No missing historical receipt is certified by these tests. Conditional enclosures retain their spectral premises, and finite-size trends retain their documented scope.

## S2 presentation successor

The S2 update carries the author-approved renderer and exact seven-PDF artwork identities in `companion/ARTWORK.json`. Run `companion/run.py verify-artwork` after publication-mode rendering in the author-approved environment to compare with that set. Standard hosted CI instead runs `verify-hosted-artwork` because the NumPy CPU path can change the last digits of S1 vector coordinates on different runners. Its S1 y tolerance is `rtol=1e-11`, `atol=0`; all S1 x coordinates and figure structure remain exact. The frozen S1 plot-data reference came from a local 7/7 exact render. The existing coordinate checks retain their numerical scope; human approval and full-manuscript review are author-side records, not conclusions supplied by CI. The source manuscript remains private. No baseline dataset, producer, cutoff, fitting window or computation result changes in this presentation update.
