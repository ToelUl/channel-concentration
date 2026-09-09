# Channel Concentration

Reproducible numerical methods and versioned evidence for channel concentration in quantum many-body systems.

This repository preserves a numerical evidence baseline independently of ongoing manuscript revisions. It includes the original computational sources, explicit numerical settings, current Potts/NNN results, bounded regression tests and source-to-result hashes.

**Scope:** the numerical evidence package has passed its scoped local checks. Full manuscript acceptance remains open. Read the [known limitations](baseline/docs/KNOWN_LIMITATIONS.md) before interpreting the results.

## Numerical evidence baseline

| Item | Identity |
|---|---|
| Baseline | `CC-NUMERICAL-BASELINE-20260909` |
| Release tag | `baseline-2026-09-09-rc1` |
| Potts producer | `cc-repro 0.5.0.dev0` |
| NNN producer | `cc-repro 0.5.1.dev0` |
| Compatible reader | `cc-repro 0.5.2.dev0` |
| Baseline manifest SHA256 | `a6020a66b641854f1345e3d11d36b19ea8812bdfae6b2161f9a8b19121385f67` |
| Packaged evidence ZIP SHA256 | `73e0a87646354f2e546bb86243b604a3e383617c1e7fe86ddb52e16fbbdb38bf` |

The [`baseline/`](baseline/) directory is the byte-preserved, verified candidate. Its pre-publication status statements describe when those files were sealed; subsequent publication information belongs to this repository and its release record. Do not edit the baseline in place to update those statements.

The evidence covers nine Potts fixed sizes, nine mandatory ladder rungs and 69 unique NNN tasks. The final NNN invocation resumed all 69 tasks and computed zero new tasks. Current postprocessing retains its original scientific premises and acceptance thresholds.

## Start here

- [Reproduction and installation instructions](baseline/docs/REPRODUCE.md)
- [Chinese verification report](baseline/verification/REPORT_zh-TW.md)
- [Source and public packaging lineage](baseline/docs/PROVENANCE.md)
- [Numerical datasets](baseline/data/)
- [Software source](baseline/software/) and [frozen producers](baseline/producers/)
- [Release downloads](https://github.com/ToelUl/channel-concentration/releases)

To verify a clone or unpacked repository archive:

```sh
python baseline/tools/verify_release.py
```

Then follow the reproduction guide from inside `baseline/`. Supported numerical runtime: Linux/WSL, Python 3.12.13 and the supplied fixed dependency versions. Strict current-result readers additionally compare the recorded platform and BLAS identity. Use the separately documented hash-inspection path on other systems; do not weaken identity checks to force acceptance.

## Verification and interpretation

Local clean installation succeeded for the wheel and source distribution of all three versions. Detached regression suites passed 45, 58 and 69 tests respectively; these suites have overlapping coverage. Five current postprocessing routes reproduced the baseline outputs. Three additional small fresh numerical routes passed. No complete large campaign was rerun for packaging.

Repository CI verifies baseline integrity and bounded software regressions on a hosted Linux runner. Its results are separate from the local large numerical evidence and strict current-result replay. The workflow does not certify full manuscript reproduction.

Manuscript sources, private local paths, host identities and unpublished artwork are excluded. A small set of nonessential derived receipts is supplied as clearly labelled public projections. Original committed numerical inputs remain unchanged.

## Versions and citation

Cite the specific release, its tag/commit and the baseline manifest SHA256. [CITATION.cff](CITATION.cff) identifies this repository's evidence baseline; software-specific citation files remain in the versioned source trees. No DOI is claimed.

Manuscript wording and layout can change while referring to this baseline. Changes to scientific computations, input selection or fitting windows require a new numerical/analysis version with an explicit difference record.

## License

Project software, documentation and project-generated numerical data use the [MIT License](LICENSE), with the [data scope](baseline/DATA_LICENSE.md) and [third-party notices](THIRD_PARTY_NOTICES.md) preserved. Vendored dependencies retain their original licenses.

## 中文

此倉庫先固定程式與數值證據，作為後續稿件修訂的依據。`baseline/` 保留原始封存內容；完整論文與出版圖面仍有未結事項，請依已知限制解讀結果。新的科學分析應另外版本化，不覆寫此數值基準。
