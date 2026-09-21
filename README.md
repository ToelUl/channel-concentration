# Channel Concentration

Numerical methods and versioned evidence for channel concentration in quantum many-body systems.

[![Numerical baseline checks](https://github.com/ToelUl/channel-concentration/actions/workflows/bounded-regression.yml/badge.svg)](https://github.com/ToelUl/channel-concentration/actions/workflows/bounded-regression.yml)
[![Companion checks](https://github.com/ToelUl/channel-concentration/actions/workflows/publication-companion.yml/badge.svg)](https://github.com/ToelUl/channel-concentration/actions/workflows/publication-companion.yml)

This repository provides computational sources, numerical settings, Potts and next-nearest-neighbor (NNN) results, bounded regression tests, and source-to-result provenance. The numerical evidence is preserved independently of manuscript revisions.

## What do you want to do?

| Task | Start here |
| --- | --- |
| Trace a result from the paper | [Figure guide](docs/FIGURE_GUIDE.md) |
| Find or regenerate a particular figure | [Companion commands](companion/README.md) and `python -B companion/run.py describe 4` |
| Inspect the numerical evidence | [Evidence classes](docs/EVIDENCE_MAP.md) and [baseline overview](docs/BASELINE.md) |
| Check files or run bounded scientific checks | [Verification scope](docs/VERIFICATION.md) and the supported commands below |
| Inspect conditional refinement bounds | [Refinement budget check](r3_support/README.md) |
| Understand evidence limits | [Known limitations](baseline/docs/KNOWN_LIMITATIONS.md) |

### Paper figure index

| Figure | Topic | Computation class |
| --- | --- | --- |
| [1](docs/FIGURE_GUIDE.md#figure-1) | TFIM–XX response and concentration | Analytic closed form |
| [2](docs/FIGURE_GUIDE.md#figure-2) | TFIM scaling and envelope | Analytic free fermion |
| [3](docs/FIGURE_GUIDE.md#figure-3) | Lifshitz directional scaling | Analytic free fermion |
| [4](docs/FIGURE_GUIDE.md#figure-4) | Potts and NNN finite-size comparisons | Archived interacting hybrid |
| [5](docs/FIGURE_GUIDE.md#figure-5) | Ranked response distributions | Archived interacting distributions |
| [6](docs/FIGURE_GUIDE.md#figure-6) | XY directional profiles | Analytic free fermion |
| [S1](docs/FIGURE_GUIDE.md#figure-s1) | Weak one-sided quench | Analytic free fermion |

The [Figure guide](docs/FIGURE_GUIDE.md) gives the scientific role, direct inputs, supporting records, and evidence limits for each figure.

## Reference documents

- [Installation and reproduction](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/docs/REPRODUCE.md)
- [Scientific and computational limitations](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/docs/KNOWN_LIMITATIONS.md)
- [Source and packaging provenance](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/docs/PROVENANCE.md)
- [Release downloads](https://github.com/ToelUl/channel-concentration/releases/tag/baseline-2026-09-09-rc1)

## Verify the files

From the repository root:

```sh
python -B baseline/tools/verify_release.py
python -B tools/verify_scientific_contracts.py
python -B companion/run.py describe 4
python -B companion/run.py render --fig 4 --output build/figure-4
```

The first command checks the distributed baseline against its manifest without
numerical calculation. The second runs all public bounded scientific
contracts, including conditional R3 CFT refinement budgets and their reviewed
interval receipt; it neither reruns the large interacting campaigns nor
establishes lattice matching or support assumptions. Use
`python -B tools/verify_scientific_contracts.py --scope refinement` for that
subset, or run its independent `r3_support/verify_refinement_budgets.py`
module directly. The remaining commands locate and regenerate one figure in a
fresh output directory. Follow the reproduction guide for numerical production
and its archived acceptance scope.

The numerical runtime is Linux/WSL with Python 3.12.13 and the supplied fixed dependencies. Strict current-result readers also check the recorded platform and BLAS identity. A successful file check on another operating system does not establish numerical runtime compatibility.

## Numerical baseline

| Item | Identity |
|---|---|
| Baseline | `CC-NUMERICAL-BASELINE-20260909` |
| Release | `baseline-2026-09-09-rc1` |
| Commit | `6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da` |
| Potts producer | `cc-repro 0.5.0.dev0` |
| NNN producer | `cc-repro 0.5.1.dev0` |
| Compatible reader | `cc-repro 0.5.2.dev0` |
| Manifest SHA256 | `a6020a66b641854f1345e3d11d36b19ea8812bdfae6b2161f9a8b19121385f67` |
| Evidence ZIP SHA256 | `73e0a87646354f2e546bb86243b604a3e383617c1e7fe86ddb52e16fbbdb38bf` |

The evidence covers nine Potts fixed sizes, nine mandatory ladder rungs, and 69 unique NNN tasks. The final NNN invocation resumed all 69 tasks and computed zero new tasks. The archived postprocessing retains its original scientific premises and acceptance thresholds.

## Verification scope

Clean local installation and detached regression tests succeeded for the wheels and source distributions of all three versions. Five current postprocessing routes reproduced the specified baseline outputs, and three additional small fresh numerical routes passed. The packaging checks did not rerun a complete large campaign.

Repository CI checks baseline integrity and bounded software regressions on Linux. Its scope is separate from strict current-result replay and final manuscript verification. See the [verification summary](docs/VERIFICATION.md) for the evidence and its limits.

## Manuscript and versioning

The immutable numerical release, approved figure presentation, and current
public wrapper have separate identities. S2 names the author's approved
renderer and seven PDF artwork identities (`2026.09.10-s2`). The subsequent
`2026.09.12-figure-names` change aligned renderer names and output filenames
with manuscript Figures 1-6 and S1. S3 names the later public navigation and
bounded-verification integration; it is not yet a versioned companion release.
[The figure map](companion/README.md#figure-and-evidence-map) lists current
names and records the frozen final-local source hashes plus validated figure
labels, numbering, and caption roles without distributing manuscript prose; [exact artwork
identities](companion/ARTWORK.json) retain the S2 approval binding. All seven
figures can be regenerated from public inputs. These public checks do not
assert a new scientific review of subsequent manuscript revisions.

The current wrapper preserves the numerical baseline and adds no
interacting-model eigensolves or fits. The manuscript text remains outside
this public companion. Its data-availability statement identifies the public
snapshot `4bf5a0c9d94bc12128b90ef7479b831401adbb99` and separately cites the
immutable numerical release; the later publication-closure companion will be
bound to its own exact content commit rather than silently changing that
historical snapshot. Until that release is fixed, no new release, DOI, arXiv
identifier or journal acceptance is asserted here.

The `baseline/` directory is immutable. Its README was sealed on 9 September 2026, before the numerical prerelease was posted. Its "Not yet published" line and note about open whole-manuscript acceptance describe that checkpoint; they are not a live status report for this repository or later manuscript revisions. The [numerical prerelease](https://github.com/ToelUl/channel-concentration/releases/tag/baseline-2026-09-09-rc1) is now public. See the [baseline overview](docs/BASELINE.md#historical-records) and [verification scope](docs/VERIFICATION.md) for the current English explanation. The original-language baseline records retain their sealed hashes.

Changes to computations, input selection, or fitting windows require a new numerical or analysis version with an explicit difference record. Presentation and documentation revisions must retain the identity of the numerical evidence they use.

## Citation

Cite the specific numerical release, its commit, and the baseline manifest SHA256. The repository's [CITATION.cff](https://github.com/ToelUl/channel-concentration/blob/main/CITATION.cff) describes the evidence baseline; software-specific citation files are included in the versioned sources. No dataset DOI has been assigned in the cited release record.

An example [BibTeX entry](docs/CITATION.bib) is provided. Cite the exact commit used for companion outputs separately from the immutable numerical baseline.

## License and support

Project software, documentation, and project-generated numerical data use the [MIT License](https://github.com/ToelUl/channel-concentration/blob/main/LICENSE), with the [data scope](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/DATA_LICENSE.md) and [third-party notices](https://github.com/ToelUl/channel-concentration/blob/main/THIRD_PARTY_NOTICES.md) preserved. Vendored dependencies retain their own licenses.

For reproducibility questions or software issues, use the [issue tracker](https://github.com/ToelUl/channel-concentration/issues). Include the release, software version, environment, command, and relevant error output.

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [changelog](CHANGELOG.md) for change and reporting conventions.
