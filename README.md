# Channel Concentration

Numerical methods and versioned evidence for channel concentration in quantum many-body systems.

[![Numerical baseline checks](https://github.com/ToelUl/channel-concentration/actions/workflows/bounded-regression.yml/badge.svg)](https://github.com/ToelUl/channel-concentration/actions/workflows/bounded-regression.yml)
[![Companion checks](https://github.com/ToelUl/channel-concentration/actions/workflows/publication-companion.yml/badge.svg)](https://github.com/ToelUl/channel-concentration/actions/workflows/publication-companion.yml)

This repository provides computational sources, numerical settings, Potts and next-nearest-neighbor (NNN) results, bounded regression tests, and source-to-result provenance. The numerical evidence is preserved independently of manuscript revisions.

## Start here

- [Baseline overview](docs/BASELINE.md)
- [Verification summary](docs/VERIFICATION.md)
- [Publication companion: regenerate seven figures and build a gallery](companion/README.md)
- [Table and evidence guide](docs/EVIDENCE_MAP.md)
- [Installation and reproduction](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/docs/REPRODUCE.md)
- [Scientific and computational limitations](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/docs/KNOWN_LIMITATIONS.md)
- [Source and packaging provenance](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/docs/PROVENANCE.md)
- [Release downloads](https://github.com/ToelUl/channel-concentration/releases/tag/baseline-2026-09-09-rc1)

## Verify the files

From the repository root:

```sh
python -B baseline/tools/verify_release.py
```

This checks the distributed baseline against its manifest. It does not run numerical calculations. Follow the reproduction guide for installation, small fresh checks, and reading the archived results.

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

The presentation companion `2026.09.12-figure-names` aligns renderer names and output filenames with manuscript Figures 1-6 and S1. It preserves all seven author-approved S2 PDF identities and all numerical inputs. [The figure map](companion/README.md#figure-and-evidence-map) lists the current names; [exact artwork identities](companion/ARTWORK.json) retain the original approval binding. All seven figures can be regenerated from public inputs. The filename update does not assert a new scientific review of subsequent manuscript revisions.

The update preserves the numerical baseline and adds no interacting-model eigensolves or fits. The manuscript text remains outside this public companion. Versioned archival citation and dedicated PRB/arXiv submission packages remain subsequent preparation steps; no new release, DOI, arXiv identifier or journal acceptance is asserted.

The `baseline/` directory is immutable. Historical records, including their original-language text and pre-publication status statements, describe the snapshot when it was sealed. Current English entry points are provided above. Updates to public documentation belong outside the frozen baseline.

Changes to computations, input selection, or fitting windows require a new numerical or analysis version with an explicit difference record. Presentation and documentation revisions must retain the identity of the numerical evidence they use.

## Citation

Cite the specific numerical release, its commit, and the baseline manifest SHA256. The repository's [CITATION.cff](https://github.com/ToelUl/channel-concentration/blob/main/CITATION.cff) describes the evidence baseline; software-specific citation files are included in the versioned sources. No dataset DOI has been assigned in the cited release record.

An example [BibTeX entry](docs/CITATION.bib) is provided. Cite the exact commit used for companion outputs separately from the immutable numerical baseline.

## License and support

Project software, documentation, and project-generated numerical data use the [MIT License](https://github.com/ToelUl/channel-concentration/blob/main/LICENSE), with the [data scope](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/DATA_LICENSE.md) and [third-party notices](https://github.com/ToelUl/channel-concentration/blob/main/THIRD_PARTY_NOTICES.md) preserved. Vendored dependencies retain their own licenses.

For reproducibility questions or software issues, use the [issue tracker](https://github.com/ToelUl/channel-concentration/issues). Include the release, software version, environment, command, and relevant error output.

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [changelog](CHANGELOG.md) for change and reporting conventions.
