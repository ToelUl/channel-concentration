# Channel Concentration — numerical evidence baseline

**Local public candidate: CC-NUMERICAL-BASELINE-20260909 / rc1. Not yet published.**

This package freezes the completed Potts/NNN numerical campaign independently of ongoing manuscript revisions. It is a scoped development release, not certification of full R3.3 manuscript reproducibility. No DOI, public repository or hosted CI result is claimed.

| Directory | Contents |
|---|---|
| `software/` | cc-repro 0.5.2.dev0 compatible reader, source and bounded tests |
| `producers/` | Exact 0.5.0.dev0 Potts and 0.5.1.dev0 NNN source/test/resource trees |
| `dist/` | Installable wheels and source distributions for all three versions |
| `data/potts/`, `data/nnn/` | Current run inputs, committed numerical records and checkpoints |
| `data/figure-inputs/` | Current Potts/NNN tables and explicitly identified analytic/reference inputs |
| `data/figure-support/` | Current CFT results, schema projection and retained controls |
| `data/nnn-postprocess/` | Current ranked-distribution output and public evidence |
| `evidence/` | Selected scoped checks from the numerical campaign |
| `environment/` | Frozen conda base specification and exact pip dependency versions |
| `provenance/` | File lineage, figure-input roles and packaging changes |
| `verification/` | Checks performed on this assembled candidate, distinct from earlier checks |

The numerical campaign includes nine Potts fixed sizes, nine mandatory ladder rungs and 69 unique NNN tasks. Original numerical methods, source identities and acceptance thresholds are retained. The final NNN invocation resumed 69 tasks and computed zero new tasks; it is not represented as one fresh 69-solve invocation.

Start with [reproduction instructions](docs/REPRODUCE.md), [known limitations](docs/KNOWN_LIMITATIONS.md), [data licensing](DATA_LICENSE.md), and [privacy/lineage policy](docs/PROVENANCE.md). The accompanying SHA256 manifest identifies exact public bytes. It detects changes; it is not a digital signature.

Manuscript, supplement, unpublished artwork, private archives, hostnames, user home paths and local job-manager logs are excluded. Numerical environment identity (Python/library/BLAS/platform versions and upstream build metadata) is retained because the existing strict readers check it. This is distinct from a private host identity.

## 中文說明

此包固定程式、數值資料與驗證範圍，作為後續稿件修訂的依據。稿件文字或排版修改可沿用此基準；若改變計算、資料選擇或擬合範圍，應另建版本，不覆寫舊證據。整體論文驗收仍有未結項目，詳見已知限制。

This baseline does not include the original seven rendered figures. Their validated input tables are supplied; manuscript-independent current seven-figure rendering remains outside this candidate's supported entrypoints. The original plotting programs remain available as source.
