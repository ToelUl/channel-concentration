# Verification summary

This English summary describes the recorded checks for numerical release `baseline-2026-09-09-rc1`. It does not replace or modify the original verification receipts. The public release and its hosted CI status were checked on 2026-09-10.

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
