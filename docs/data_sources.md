# Data sources

| Data | Provider | Version / years | How it is obtained | Used for |
|---|---|---|---|---|
| Reporting Carrier On-Time Performance | U.S. Bureau of Transportation Statistics (TranStats) | 2023-2025, monthly files | Notebook 01, cell 2 (PREZIP download) | Flights, taxi-out, taxi-in, delays |
| GHCNh hourly weather | NOAA National Centers for Environmental Information | 2023-2025, 10 airport stations | Notebook 01, cell 3 | Weather at departure hour (UTC) |
| Airports and runways | OurAirports (davidmegginson/ourairports-data) | Live dataset, downloaded at each run | Notebook 01, cell 4 | Airport metadata |
| Schedule B-43 aircraft inventory (Form 41) | U.S. Bureau of Transportation Statistics (TranStats) | 2023-2025 | Notebook 01, cell 5 (TranStats download form) | Tail number -> aircraft model |
| ICAO Aircraft Engine Emissions Databank | ICAO, hosted by EASA | Issue 32 (03/2026), `edb-emissions-databank_v32 (web).xlsx` | Manual download from easa.europa.eu; processed by `scripts/build_aircraft_engine_fuel.py` into `reference/aircraft_engine_fuel.csv` | Idle (7% thrust) fuel flow per engine |
| CO2 emission factor | ICAO Carbon Emissions Calculator Methodology | 3.16 kg CO2 per kg jet fuel | Constant in notebook 01 | Fuel -> CO2 |

Superseded: NOAA ISD-Lite (used in EM06DS). Its 2025 files end on 27 Aug 2025 and the product is retired.
EASA download page: https://www.easa.europa.eu/en/domains/environment/icao-aircraft-engine-emissions-databank
