# Thesis changes log

The EM06DS project (May 2026) is kept unchanged at git tag `em06ds-submission`.
The reproduced baseline, with only the fixes needed to run it again, is at tag `phase-a-reproduced`.
Every later change is listed here with its reason and its measured effect.
Original data tables are kept frozen in schema `new.airgreenops_em06ds` for before/after comparison.

| ID | Date | Notebook / cell | Change | Reason | Effect (before -> after) | Commit |
|---|---|---|---|---|---|---|
| A1 | 2026-10-21 | 01 / cell 3 | NOAA ISD-Lite download URL | Source moved to NOAA Open Data on AWS | Reproduction only; counts identical to May | e388f95 |
| A2 | 2026-10-22 | 02 / cell 10 | `DoubleType` -> `T.DoubleType` | Missing import; relied on session state | Reproduction only | caaab86 |
| A3 | 2026-10-22 | 02 / cell 11 | `auc()` -> `roc_auc_score()` | sklearn `auc` overwritten by a float | Reproduction only | 92f47c2 |
| A4 | 2026-10-22 | cluster | seaborn 0.13.2 | `legend=False` needs seaborn >= 0.13 | Reproduction only | b708910 |
| B1 | 2026-10-22 | 01 / cell 13 | Weather joined on UTC hour (airport time zone, DST-aware) | BTS times are local, NOAA hours are UTC; old join was 5-8 h off | Pending run | (this commit) |

Details of the reproduction: `docs/reproduction_log.md`.
