# AirGreenOps: Reducing Airport Ground Emissions Through Sustainable and Efficient Operations

MSc Data Science thesis, Emirates Aviation University.
Author: Abdulla Mohammed Abdulla Almulla.

This repository extends the AirGreenOps lakehouse built for EM06DS (Big Data Analytics and Data Visualisation, May 2026)
into a thesis-scale study of airport ground-operation emissions.

## Research questions
1. How do aircraft type, fuel use, operating weight, taxi time, weather and congestion influence ground emissions?
2. Which airports have better ground carbon performance under comparable conditions, and what are they doing differently?
3. Which changes can reduce emissions without increasing delays, extending turnaround times or restricting capacity?

## Platform
| Layer | Tool |
|---|---|
| Compute | Databricks (serverless), Apache Spark / PySpark |
| Storage | Delta Lake, Unity Catalog volumes (Bronze / Silver / Gold) |
| Modelling | Spark MLlib |
| Dashboard | Gradio, deployed as a Databricks App |
| Version control | Git / GitHub |
| References | Mendeley Reference Manager, Harvard style |

## Notebooks (run in order)
| Notebook | Purpose |
|---|---|
| `01_airgreenops_ingestion_etl.ipynb` | Obtain and scrub: BTS, NOAA, OurAirports, aircraft reference → Bronze/Silver/Gold. Exploratory analysis. |
| `02_airgreenops_mlp_tuning_benchmark.ipynb` | Model: MLP training, tuning and scalability benchmark. |
| `03_airgreenops_app.ipynb` | Delay-risk model, explainability (XAI), Gradio dashboard. |

The commits of 9 May 2026 hold the EM06DS submission (notebooks, figures and reports, now in `docs/em06ds/`).
Later commits record each thesis change, so the history shows what changed and why.

## Data sources
| Data | Source |
|---|---|
| Flight records 2023-2025 | U.S. Bureau of Transportation Statistics, TranStats On-Time Reporting |
| Hourly weather | NOAA National Centers for Environmental Information |
| Airports and runways | OurAirports |
| Fuel and CO2 reference | ICAO (CO2 factor 3.16 kg per kg fuel) |

Emissions are estimated from reference values, not measured.
