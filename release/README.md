# Release closure assets

This directory stores the schemas, generators, and candidate metadata needed
to close the current publication companion. It does not contain a completed
release or manuscript source.

The author-approved GitHub prerelease-candidate name is
`companion-2026-09-21-rc1`, as recorded in `RELEASE_CANDIDATE.json`. Internal
stage names such as S2, S3, and R6a are not release names: S2 identifies the
approved renderer/artwork authority, while the immutable numerical authority
remains `baseline-2026-09-09-rc1`. The author's public-transition authorization
is limited to the repository branch, pull request, exact tag, and GitHub
prerelease; it does not authorize a DOI, external archive publication, arXiv
submission, or journal submission.

The [candidate release notes](RELEASE_NOTES.md) describe only the bounded
companion content and retain the documented evidence limits.
`MANUSCRIPT_TARGET.json` records only the approved hashes of the three frozen
TeX sources and three final PDFs; it does not distribute manuscript content.

## Non-circular generation order

1. Commit the release content, including these schemas and generators.
2. Generate `RELEASE_CONTENT_MANIFEST.json` from that exact commit with
   `tools/generate_release_manifest.py`.
3. Complete exact-commit verification and save JSON receipts with `PASS`
   status.
4. Generate `MANUSCRIPT_BINDING.json` with
   `tools/generate_manuscript_binding.py`, supplying the frozen manuscript
   root, final build root, release manifest, and verification receipts. The
   generator refuses sources or PDFs that differ from `MANUSCRIPT_TARGET.json`.
5. Publish the two generated JSON files only as release-candidate/release
   assets unless a later commit deliberately binds them.

Both generators refuse to overwrite an existing output and refuse an output
path tracked by the bound content commit. This prevents either asset from
claiming to hash itself through the same Git commit.

No command here creates a tag, pushes a branch, publishes a release, uploads a
DOI/archive record, or changes the immutable baseline.
