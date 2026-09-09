# Provenance and public packaging

`provenance/FILE_LINEAGE.json` binds each selected file to its original SHA256 and records byte preservation or public projection. `provenance/FIGURE_INPUTS.json` identifies current, analytic and historical/reference input roles. `MANIFEST.json` covers the final candidate's files, including release documentation, tools and distributions. `SHA256SUMS` also binds the manifest itself.

The original R3.3 source ZIP has SHA256 `89fa948035e5ea57adec6d8e8e51312b63b842644381275f470fc73ee165be37`. The ZIP and manuscript sources are not included. The runtime's separate nested-source hashes are preserved in its existing resource manifests; these are different objects and must not be confused with the outer ZIP hash.

Runtime `.py`, resource, numerical configuration, existing test and compatibility registry bytes are unchanged for each of the three package versions. Release README/docs are newly assembled. Stale internal verification folders, excluded-manuscript filename inventories, workstation paths, job-control scripts, local launch logs and whole archive files are not bundled. Public packaging changes do not change old result producer identities.

Private paths in selected nonessential derived receipts are redacted only in new public JSON projections. Numeric values are retained, and the old SHA256 remains a reference to the private original; it is not asserted to match the projection. No altered projection is used to manufacture an original seal. The raw Potts/NNN inputs used by the replay helper are byte-identical.

Numerical environment records retain upstream build paths, for example NumPy's OpenBLAS build metadata, where these are part of the original identity. They are dependency build facts, not this researcher's home directory. Original third-party author names, public metadata and licenses are preserved.

After publication, use the actual archived identifier plus the manifest SHA256 in manuscript/data-availability records. This candidate invents no permanent identifier. A later manuscript correction does not change these frozen data; a changed scientific analysis requires a new version and a difference record.
