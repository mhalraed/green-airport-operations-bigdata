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
| B1 | 2026-10-22 | 01 / cell 13 | Weather joined on UTC hour (airport time zone, DST-aware) | BTS times are local, NOAA hours are UTC; old join was 5-8 h off | Warmest local hour (season-adjusted): 19-23 h -> 13-16 h at all 10 airports. corr(rain, taxi-out) 0.024 -> 0.056; corr(wind, taxi-out) 0.056 -> 0.080; corr(rain, departure delay) 0.038 -> 0.070. Mean taxi-out wet vs dry hours: +3.3 min -> +6.1 min. Rows unchanged (20,588,136); weather coverage unchanged (88.1%, ISD-Lite 2025 ends 27 Aug) | 4f70668 |
| B2 | 2026-10-23 | 01 / cells 3, 6, 10 | Weather source ISD-Lite -> NOAA GHCNh hourly; NOAA quality flags applied (letter codes and legacy 2/3/6/7 removed); hourly precipitation = last report in hour, trace = 0 mm; other variables = hourly mean | ISD-Lite 2025 files end 27 Aug 2025 (11.9% of flights at the 10 airports had no weather); ISD-Lite is retired and replaced by GHCNh; old code read trace precipitation (-1) as -0.1 mm | Weather coverage at 10 airports 88.1% -> 99.5% (2025: 65.2% -> 98.7%; Sep-Dec 2025: 0% -> 98.1%). Negative precipitation rows 263,685 -> 0. QC removed 0.025% of temperature and 0.007% of wind observations. Warmest hour still 12-15 h local. Cumulative vs May (B1+B2): corr(rain, taxi-out) 0.024 -> 0.088; corr(wind, taxi-out) 0.056 -> 0.086; wet-hour taxi-out penalty +3.3 -> +7.0 min | b887e2d, 7860dc5 |
| B2a | 2026-10-23 | 01 / cells 3, 6 | GHCNh station column name `STATION` (was coded as `Station_ID`) | Wrong header name; first B2 run rejected all files. All other column names verified against a real file | Fix for B2 only | 7860dc5 |
| B4 | 2026-10-23 | 01 / cells 9, 13, new cell 49 | Keep arrival columns (taxi-in, arrival delay, scheduled arrival hour, arrivals per hour); taxi-in CO2 and avoidable taxi-in CO2 per flight (same method as taxi-out); new Gold table `gold_airport_ground_co2` = taxi-out at origin + taxi-in at destination, with CO2 per movement | EM06DS kept only departure columns, so about a third of taxi time (taxi-in) was missing; proposal scope includes taxi-in | Taxi-in present for 100% of flights. Taxi-in = 31.8% of total taxi CO2 (2023-2025). Across airports with >=50k movements the taxi-in share ranges 20.4% (BUR) to 40.6% (ORD). Ranking of the 30 busiest airports: taxi-out per departure vs total per movement, rank correlation 0.93, 12 airports move >=3 places (largest: DFW 15th -> 6th). Silver 57 columns, Gold 77 columns, 341 airports in gold_airport_ground_co2 | b7027b3 |

Details of the reproduction: `docs/reproduction_log.md`.

## B1 validation method
Physical check: air temperature should peak in mid-afternoon local time. For each of the 10 weather airports,
temperature was expressed as the difference from the same airport-day mean (removes seasonal flight mix),
averaged by scheduled local departure hour (hours with at least 2,000 flights), and the warmest hour taken.
EM06DS join: 19:00-23:00 (shifted by the UTC offset). After B1: 13:00-16:00 at every airport.
Compared tables: `new.airgreenops_em06ds.silver_flight_weather_features` (frozen) vs `new.airgreenops.silver_flight_weather_features`.

## B2 note on precipitation coverage
Precipitation is present for 87.5% of flight-hours at the 10 airports (temperature 99.5%). GHCNh reports
precipitation only in observations that carry a precipitation group; hours without one are left missing
(unknown), not set to zero.

## B4 note
Fuel burn per minute for both taxi-out and taxi-in still comes from the EM06DS distance-based aircraft group
(4-row reference table). Airport CO2 per movement therefore still partly reflects route length mix. B3 replaces
this with aircraft type from tail number and ICAO engine fuel flow.
