# Reproduction log

Goal: re-run the EM06DS notebooks (May 2026) unchanged on a newly built workspace and compare results.

**Environment (October 2026):** Databricks on AWS (us-east-1), classic workspace, Unity Catalog `new.airgreenops.project_data`.
Cluster: Databricks Runtime 15.4 LTS (Spark 3.5.0), 1 driver + 2 workers, m5d.xlarge. See `environment/`.

## Notebook 01: ingestion and ETL

| Output | May 2026 | Oct 2026 | Match |
|---|---|---|---|
| Bronze BTS rows | 20,928,703 | 20,928,703 | Yes |
| NOAA files / rows | 30 / 232,345 | 30 / 232,345 | Yes |
| Silver flights | 20,588,136 | 20,588,136 | Yes |
| Silver feature table | 20,588,136 x 44 | 20,588,136 x 44 | Yes |
| Gold table | 20,588,136 x 64 | 20,588,136 x 64 | Yes |
| OurAirports bronze / silver | 85,332 / 9,057 | 86,258 / 9,052 | No: live source, updated daily |

Note: Bronze BTS includes 124 non-flight rows. Each BTS zip contains `readme.html` (125 lines); unzipping all
months into one folder leaves one copy, which Spark reads as CSV (1 header + 124 rows). These rows are removed
by the Silver filters, so Silver and Gold counts are unaffected.

## Notebook 02: MLP training and benchmark

| Model | May 2026 AUC | Oct 2026 AUC (validation) |
|---|---|---|
| Baseline MLP | 0.691 | 0.686 |
| Deep MLP | 0.697 | 0.691 |
| Wide MLP | 0.682 | 0.678 |

Differences come from the random 1M-row training sample. Model ranking is unchanged.
Positive class ("high emission") share of validation data: about 25%.

## Changes needed to reproduce

| Commit | Notebook | Change | Reason |
|---|---|---|---|
| e388f95 | 01 | NOAA ISD-Lite URL | NCEI moved the files to NOAA Open Data on AWS (`noaa-isd-pds`); old URL returned an HTML page |
| caaab86 | 02 | `DoubleType` -> `T.DoubleType` | Name was never imported; May run relied on interactive session state |
| 92f47c2 | 02 | `auc(fpr, tpr)` -> `roc_auc_score(...)` | Training cells overwrote `sklearn.metrics.auc` with a float |
| (environment) | 02 | seaborn 0.13.2 on cluster | `legend=False` in `sns.barplot` needs seaborn >= 0.13 |
