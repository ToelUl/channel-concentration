# Changelog

## 2026.09.12-figure-names - Manuscript numbering alignment

- Renamed the four legacy output stems for Figures 4, 5, 6 and S1 to match the current manuscript and existing renderer functions.
- Updated the figure map, artwork inventory, packaging paths and English documentation.
- Added refusal checks and regression tests for figure-number and renderer/filename mismatches.
- Kept all renderer function bodies, seven approved PDF hashes, numerical inputs and the immutable baseline unchanged. Existing scripts using old filenames should adopt the current figure map and a fresh output directory.

## 2026.09.10-s2 — Approved presentation successor

- Adopted the exact S2 renderer, source-derived figure mappings and seven human-approved PDF identities.
- Improved contrast, type size, marker presentation and Figure 4 legend spacing; retained all interacting samples and clarified the Figure 5 retained-rank legend.
- Added explicit artwork-identity verification and updated the English documentation to the completed S2 review state.
- Preserved numerical baseline files, all data inputs, fitting windows and computation identities. No new fit or interacting-model eigensolve was performed.

This commit does not create a new numerical release or DOI, distribute the manuscript, or complete venue-specific submission packaging.

## 2026.09.10-s1 — Submission preparation companion

- Added a complete English documentation path, including baseline and verification summaries.
- Added the byte-preserved R3.7 rendering implementation with a portable public entry point, input hashes and source-derived figure mappings.
- Added checks for 16 rendered interacting-model data bindings and a minimal LaTeX figure gallery.
- Added companion CI and contribution/reporting guidance.
- Preserved all numerical baseline files and the original producer/reader identities.

This preparation change adds no interacting-model eigensolves or fits. It is not the final manuscript/artwork release, and it does not assign an article or dataset DOI.

## baseline-2026-09-09-rc1 — Numerical evidence baseline

The immutable baseline contains the original Potts and NNN producers, compatible reader, numerical inputs/results, fixed environment specifications, tests and verification receipts. Its original release remains a prerelease and is not replaced by the preparation companion.
