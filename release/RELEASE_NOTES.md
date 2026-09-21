# companion-2026-09-21-rc1 prerelease notes

Status: author-approved GitHub prerelease candidate. The tag target, release
page, and attached assets are authoritative for publication status. No DOI,
external archive publication, arXiv submission, or journal acceptance is
asserted by this file.

## Purpose

This candidate is the publication companion for the frozen final-local
manuscript identities. It provides a direct route from every manuscript figure
(Figures 1–6 and S1) to its scientific calculation or archived-input lineage,
intermediate transformation where applicable, and publication renderer. It
also provides bounded integrity and scientific checks without redistributing
the manuscript prose.

## Included changes

- Complete human- and machine-readable figure-to-code routes, including the
  distinct expensive-producer, postprocessor, archived-replay, projection, and
  rendering stages for Figures 4 and 5.
- Figure Map alignment with the three frozen final-local TeX source hashes,
  figure labels, output filenames, numbering, and caption roles.
- Bounded scientific-contract and artist-coordinate checks, including
  registered finite-grid error ceilings and an independent weak-quench
  coefficient oracle.
- Deterministic exact-commit release-manifest generation and a non-circular
  manuscript-binding schema and generator. The generator checks the three
  frozen TeX and three final PDF identities against a tracked hash-only target.

## Authority separation

| Layer | Identity | Scope |
| --- | --- | --- |
| Publication companion | `companion-2026-09-21-rc1` | Navigation, selected rendering, bounded checks, documentation, and release provenance. |
| Numerical evidence | `baseline-2026-09-09-rc1` at `6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da` | Immutable archived numerical inputs, outputs, producer/reader software, and baseline receipts. |
| Artwork | `2026.09.12-figure-names` with S2-approved identities | Frozen renderer lineage and seven author-approved PDF hashes. |
| Manuscript | Generated `MANUSCRIPT_BINDING.json` | Frozen source/PDF hashes and figure-label alignment; manuscript prose is not distributed here. |

The exact companion content commit and full tracked-file SHA-256 inventory are
recorded by a generated `RELEASE_CONTENT_MANIFEST.json` after the source commit
is fixed. The generated `MANUSCRIPT_BINDING.json` records that manifest and the
named final verification receipts. Both are release assets rather than tracked
members of the commit that they identify.

## Evidence limits

This candidate adds no interacting-model eigensolve, numerical input selection,
fit, cutoff, or thermodynamic-convergence claim. It does not repair missing
historical receipts, establish conditional lattice/support premises, or turn a
portable artwork check into exact seven-PDF reproduction. Final release assets
must disclose any failed, skipped, or platform-dependent check.
