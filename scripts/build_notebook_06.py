"""Builds notebooks/06_rq3_operational_scenarios.ipynb (RQ3: emission reductions without more delay or less capacity)."""
import json

OUT = "notebooks/06_rq3_operational_scenarios.ipynb"
cells = []


def md(t):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": t})


def code(t):
    cells.append({"cell_type": "code", "execution_count": 0, "metadata": {}, "outputs": [], "source": t})


md("""# RQ3: Which changes reduce ground emissions without more delay or less capacity?

Research question 3: Which changes can reduce emissions without increasing delays, extending turnaround times or restricting capacity?

Scenarios on observed 2025 flights at the 76 major airports (notebook 05):
1. **Gate hold / departure metering**: part of the queue time above the unimpeded taxi-out time is spent at the gate with engines off.
   Wheels-off times stay the same, so departure delay and runway throughput do not change by construction.
2. **Single-engine taxi**: one engine is shut down during taxi, except for engine warm-up before take-off and cool-down after landing.
   Taxi times do not change.
3. **Ground power at the stand**: gate electricity (ground power and pre-conditioned air) replaces part of the APU running time during
   turnaround. Turnaround times are measured from the data by linking each arrival to the next departure of the same tail number.
4. **Combined**: 1 + 2 + 3, with single-engine taxi applied to the taxi time that remains after the gate hold.

Fuel burn per taxi minute comes from the ICAO engine databank (notebook 01). The other inputs are **assumptions** with a low, central and
high value. They are placeholders to be justified from the literature (e.g. ICAO Doc 9889 for APU fuel flow; studies of pushback rate
control, single-engine taxi and gate electrification). All results are estimates, not measured savings.""")

code("""# Imports, configuration and scenario assumptions
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pyspark.sql import functions as F
from pyspark.sql.window import Window

CATALOG = "new"
SCHEMA = "airgreenops"
spark.sql(f"USE CATALOG `{CATALOG}`")
spark.sql(f"USE SCHEMA `{SCHEMA}`")

CO2 = 3.16
YEAR = 2025
WEATHER_AIRPORTS = ["LAX", "SFO", "SEA", "LAS", "DEN", "ORD", "DFW", "ATL", "MIA", "JFK"]
MAJOR_AIRPORTS = sorted(r["airport"] for r in spark.table("rq2_airport_ranking").select("airport").collect())
GROUPS = ["regional_jet", "narrow_body", "wide_body"]

# Assumptions: (low, central, high). Low/high are chosen so that "low" gives the smaller saving.
A = {
    "hold_share":        (0.25, 0.50, 0.75),   # share of excess taxi-out queue time that can be moved to the gate
    "set_saving":        (0.30, 0.40, 0.50),   # share of taxi fuel saved per eligible single-engine minute
    "warmup_min":        (5, 3, 2),            # minutes on two engines before take-off (more minutes = less saving)
    "cooldown_min":      (5, 3, 2),            # minutes on two engines after landing
    "set_eligible_other": (0.70, 0.85, 0.95),  # share of flights eligible at airports without weather data
    "apu_share_of_turn": (0.30, 0.50, 0.80),   # share of turnaround time the APU runs today (baseline)
    "apu_min_with_gpu":  (15, 10, 5),          # APU minutes still needed per turn with ground power (start-up, checks)
    "grid_kg_per_kwh":   (0.45, 0.37, 0.25),   # grid CO2 intensity for ground power
}
APU_FUEL_KG_MIN = {"regional_jet": (0.8, 1.0, 1.3), "narrow_body": (1.5, 1.9, 2.3), "wide_body": (3.5, 4.5, 5.5)}
GPU_KW = {"regional_jet": (39, 30, 21), "narrow_body": (65, 50, 35), "wide_body": (156, 120, 84)}   # electricity demand at the gate
print("Major airports:", len(MAJOR_AIRPORTS))
pd.DataFrame([{"assumption": k, "low": v[0], "central": v[1], "high": v[2]} for k, v in A.items()])""")

code("""# Unimpeded taxi-out time per airport and aircraft class, from 2023-2024 low-traffic hours
# Low traffic = hours with departures at or below the airport's 25th percentile of hourly departures.
gold = spark.table("gold_flight_emissions_clean")
hist = gold.where(F.col("year").isin(2023, 2024) & F.col("origin").isin(MAJOR_AIRPORTS) & F.col("taxi_out_clean").isNotNull())

low_traffic = hist.groupBy("origin").agg(F.expr("percentile_approx(airport_hour_departure_count, 0.25)").alias("low_traffic_max"))
unimpeded = (
    hist.join(low_traffic, "origin")
    .where(F.col("airport_hour_departure_count") <= F.col("low_traffic_max"))
    .groupBy("origin", "aircraft_group")
    .agg(F.expr("percentile_approx(taxi_out_clean, 0.20)").alias("unimpeded_taxi_out"), F.count("*").alias("low_traffic_flights"))
)
unimpeded.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq3_unimpeded_taxi_out")
display(unimpeded.orderBy("origin", "aircraft_group").limit(30))""")

code("""# Departure-side and arrival-side flight data for 2025

# Gate demand: hours when an airline has at least as many arrivals as departures at the airport.
# In those hours its gates are likely needed for arriving aircraft, so a gate hold may block an arrival.
airline_deps = gold.groupBy(F.col("origin").alias("airport"), "flight_date", F.col("scheduled_dep_hour").alias("hour"), "airline").agg(F.count("*").alias("airline_deps"))
airline_arrs = gold.groupBy(F.col("dest").alias("airport"), "flight_date", F.col("scheduled_arr_hour").alias("hour"), "airline").agg(F.count("*").alias("airline_arrs"))

dep = (
    gold.where((F.col("year") == YEAR) & F.col("origin").isin(MAJOR_AIRPORTS) & F.col("taxi_out_clean").isNotNull())
    .join(unimpeded.select("origin", "aircraft_group", "unimpeded_taxi_out"), ["origin", "aircraft_group"], "left")
    .withColumn("airport", F.col("origin"))
    .withColumn("hour", F.col("scheduled_dep_hour"))
    .join(airline_deps, ["airport", "flight_date", "hour", "airline"], "left")
    .join(airline_arrs, ["airport", "flight_date", "hour", "airline"], "left")
    .fillna({"airline_arrs": 0})
    .withColumn("gate_peak", (F.col("airline_arrs") >= F.col("airline_deps")).cast("int"))
    .withColumn("excess_out", F.greatest(F.col("taxi_out_clean") - F.coalesce(F.col("unimpeded_taxi_out"), F.col("taxi_out_clean")), F.lit(0.0)))
    # Single-engine taxi eligibility from weather at the 10 weather airports: not in rain and above 3 deg C
    .withColumn(
        "set_weather",
        F.when(~F.col("origin").isin(WEATHER_AIRPORTS), F.lit("unknown"))
         .when(((F.col("precipitation_1hr") > 0) & (F.col("precipitation_1hr_missing") == 0)) | (F.col("air_temperature") <= 3), F.lit("not_eligible"))
         .otherwise(F.lit("eligible"))
    )
    .select("airport", "aircraft_group", "fuel_burn_kg_per_min", "taxi_out_clean", "excess_out", "gate_peak", "set_weather")
    .cache()
)

arr = (
    gold.where((F.col("year") == YEAR) & F.col("dest").isin(MAJOR_AIRPORTS) & F.col("taxi_in_clean").isNotNull())
    .select(F.col("dest").alias("airport"), "aircraft_group", "fuel_burn_kg_per_min", "taxi_in_clean")
    .cache()
)
print(f"{YEAR} departures: {dep.count():,} | arrivals: {arr.count():,}")""")

code("""# Turnaround times: gate arrival of one flight to gate departure of the next flight of the same aircraft
sf = spark.table("silver_flights")
aircraft = spark.table("silver_aircraft").select("tail_number", "size_class")

def ts(date_col, hhmm_col, delay_col, add_day=None):
    base = F.unix_timestamp(F.col(date_col).cast("timestamp"))
    t = base + (F.floor(F.col(hhmm_col) / 100) % 24) * 3600 + (F.col(hhmm_col) % 100) * 60 + F.coalesce(F.col(delay_col), F.lit(0.0)) * 60
    return t + (F.when(add_day, 86400).otherwise(0) if add_day is not None else 0)

legs = (
    sf.where(F.col("year").isin(YEAR - 1, YEAR) & F.col("tail_number").isNotNull())
    .withColumn("tail_number", F.upper(F.trim(F.col("tail_number"))))
    .withColumn("gate_out", ts("flight_date", "scheduled_dep_time", "dep_delay"))
    .withColumn("gate_in", ts("flight_date", "scheduled_arr_time", "arr_delay", add_day=F.col("scheduled_arr_time") < F.col("scheduled_dep_time")))
    .select("tail_number", "origin", "dest", "year", "distance", "gate_out", "gate_in")
)
w = Window.partitionBy("tail_number").orderBy("gate_out")
turns = (
    legs
    .withColumn("prev_dest", F.lag("dest").over(w))
    .withColumn("prev_gate_in", F.lag("gate_in").over(w))
    .where((F.col("year") == YEAR) & (F.col("prev_dest") == F.col("origin")) & F.col("origin").isin(MAJOR_AIRPORTS))
    .withColumn("turn_min", (F.col("gate_out") - F.col("prev_gate_in")) / 60)
    .where(F.col("turn_min").between(20, 240))   # same-day turns; longer gaps are overnight or schedule breaks
    .join(aircraft, "tail_number", "left")
    .withColumn(
        "aircraft_group",
        F.coalesce(F.col("size_class"),
                   F.when(F.col("distance") < 500, "regional_jet").when(F.col("distance") < 2500, "narrow_body").otherwise("wide_body"))
    )
    .select(F.col("origin").alias("airport"), "aircraft_group", "turn_min")
    .cache()
)
turn_summary = turns.groupBy("aircraft_group").agg(F.count("*").alias("turns"), F.round(F.avg("turn_min"), 1).alias("mean_turn_min"),
                                                    F.expr("percentile_approx(turn_min, 0.5)").alias("median_turn_min")).toPandas()
print(turn_summary.to_string(index=False))""")

code("""# Aggregate the components each scenario needs, per airport and aircraft class (computed once in Spark)

dep_agg = (
    dep.groupBy("airport", "aircraft_group")
    .agg(
        F.count("*").alias("departures"),
        F.sum(F.col("taxi_out_clean") * F.col("fuel_burn_kg_per_min")).alias("out_fuel_kg"),
        F.sum(F.col("excess_out") * F.col("fuel_burn_kg_per_min")).alias("excess_fuel_kg"),
        F.sum("excess_out").alias("excess_min"),
        F.sum(F.col("excess_out") * F.col("fuel_burn_kg_per_min") * (1 - F.col("gate_peak"))).alias("excess_fuel_kg_offpeak"),
        F.sum(F.col("excess_out") * (1 - F.col("gate_peak"))).alias("excess_min_offpeak"),
        F.avg("gate_peak").alias("gate_peak_share"),
        *[F.sum(F.when(F.col("set_weather") == s, F.greatest(F.col("taxi_out_clean") - wu, F.lit(0.0)) * F.col("fuel_burn_kg_per_min")).otherwise(0)).alias(f"set_out_fuel_{s}_w{wu}")
          for s in ["eligible", "unknown"] for wu in sorted(set(A["warmup_min"]))],
        *[F.sum(F.when(F.col("set_weather") == s, F.greatest(F.col("taxi_out_clean") - F.col("excess_out") * h - wu, F.lit(0.0)) * F.col("fuel_burn_kg_per_min")).otherwise(0)).alias(f"set_out_fuel_{s}_w{wu}_h{int(round(h * 100))}")
          for s in ["eligible", "unknown"] for wu in sorted(set(A["warmup_min"])) for h in sorted(set(A["hold_share"]))],
    )
    .toPandas()
)

arr_agg = (
    arr.groupBy("airport", "aircraft_group")
    .agg(
        F.count("*").alias("arrivals"),
        F.sum(F.col("taxi_in_clean") * F.col("fuel_burn_kg_per_min")).alias("in_fuel_kg"),
        *[F.sum(F.greatest(F.col("taxi_in_clean") - cd, F.lit(0.0)) * F.col("fuel_burn_kg_per_min")).alias(f"set_in_fuel_c{cd}")
          for cd in sorted(set(A["cooldown_min"]))],
    )
    .toPandas()
)

turn_agg = (
    turns.groupBy("airport", "aircraft_group")
    .agg(
        F.count("*").alias("turns"),
        F.sum("turn_min").alias("turn_min_total"),
        *[F.sum(F.greatest(F.col("turn_min") * s - m, F.lit(0.0))).alias(f"apu_avoid_min_s{int(round(s * 100))}_m{m}")
          for s in sorted(set(A["apu_share_of_turn"])) for m in sorted(set(A["apu_min_with_gpu"]))],
    )
    .toPandas()
)
print("Components ready:", len(dep_agg), len(arr_agg), len(turn_agg), "airport-class rows")""")

code("""# Scenario calculator: kg CO2 saved per airport for any combination of assumptions

def scenario(p):
    \"\"\"p: dict with one value per assumption (and group-specific APU / GPU values). Returns per-airport savings (kg CO2).\"\"\"
    d = dep_agg.copy()
    a = arr_agg.copy()
    t = turn_agg.copy()
    apu = d["aircraft_group"].map(p["apu_fuel"])
    kw = d["aircraft_group"].map(p["gpu_kw"])

    # 1) Gate hold: saved taxi fuel minus the power used at the gate while holding (ground power, as in the stand scenario)
    hold_fuel = p["hold_share"] * d["excess_fuel_kg"]
    hold_min = p["hold_share"] * d["excess_min"]
    d["s1_kg"] = hold_fuel * CO2 - hold_min / 60 * kw * p["grid_kg_per_kwh"]
    # Conservative variant: no holds in hours when the airline needs its gates for arrivals
    d["s1_offpeak_kg"] = p["hold_share"] * d["excess_fuel_kg_offpeak"] * CO2 - p["hold_share"] * d["excess_min_offpeak"] / 60 * kw * p["grid_kg_per_kwh"]

    # 2) Single-engine taxi on taxi-out (weather-eligible flights) and taxi-in
    wu, cd = p["warmup_min"], p["cooldown_min"]
    out_elig = d[f"set_out_fuel_eligible_w{wu}"] + p["set_eligible_other"] * d[f"set_out_fuel_unknown_w{wu}"]
    d["s2_out_kg"] = p["set_saving"] * out_elig * CO2
    a["s2_in_kg"] = p["set_saving"] * p["set_eligible_other"] * a[f"set_in_fuel_c{cd}"] * CO2

    # Single-engine taxi on the taxi-out time that remains after the gate hold (for the combined scenario)
    h = int(round(p["hold_share"] * 100))
    out_elig_after = d[f"set_out_fuel_eligible_w{wu}_h{h}"] + p["set_eligible_other"] * d[f"set_out_fuel_unknown_w{wu}_h{h}"]
    d["s2_out_after_hold_kg"] = p["set_saving"] * out_elig_after * CO2

    # 3) Ground power at the stand: APU minutes avoided x (APU CO2 - electricity CO2)
    s, m = int(round(p["apu_share_of_turn"] * 100)), p["apu_min_with_gpu"]
    avoid = t[f"apu_avoid_min_s{s}_m{m}"]
    t_apu = t["aircraft_group"].map(p["apu_fuel"])
    t_kw = t["aircraft_group"].map(p["gpu_kw"])
    t["s3_kg"] = avoid * (t_apu * CO2 - t_kw / 60 * p["grid_kg_per_kwh"])
    # Baseline APU CO2 during turnarounds (depends on the assumed APU running share and fuel flow)
    t["apu_baseline_kg"] = t["turn_min_total"] * p["apu_share_of_turn"] * t_apu * CO2

    out = (
        d.groupby("airport")[["departures", "out_fuel_kg", "s1_kg", "s1_offpeak_kg", "s2_out_kg", "s2_out_after_hold_kg", "gate_peak_share"]]
        .agg({"departures": "sum", "out_fuel_kg": "sum", "s1_kg": "sum", "s1_offpeak_kg": "sum", "s2_out_kg": "sum",
              "s2_out_after_hold_kg": "sum", "gate_peak_share": "mean"})
        .join(a.groupby("airport")[["arrivals", "in_fuel_kg", "s2_in_kg"]].sum(), how="outer")
        .join(t.groupby("airport")[["turns", "s3_kg", "apu_baseline_kg"]].sum(), how="outer")
        .fillna(0)
    )
    out["baseline_taxi_co2_kg"] = (out["out_fuel_kg"] + out["in_fuel_kg"]) * CO2
    out["baseline_ground_co2_kg"] = out["baseline_taxi_co2_kg"] + out["apu_baseline_kg"]
    out["s2_kg"] = out["s2_out_kg"] + out["s2_in_kg"]
    out["combined_kg"] = out["s1_kg"] + out["s2_out_after_hold_kg"] + out["s2_in_kg"] + out["s3_kg"]
    return out


def pick(level):
    i = {"low": 0, "central": 1, "high": 2}[level]
    p = {k: v[i] for k, v in A.items()}
    p["apu_fuel"] = {g: APU_FUEL_KG_MIN[g][i] for g in GROUPS}
    p["gpu_kw"] = {g: GPU_KW[g][i] for g in GROUPS}
    return p

print("Scenario calculator ready")""")

code("""# National results for 2025 (76 major airports): tonnes CO2 saved per year, low / central / high

rows = []
for level in ["low", "central", "high"]:
    r = scenario(pick(level)).sum(numeric_only=True)
    base = r["baseline_ground_co2_kg"]
    for name, col in [("1 Gate hold", "s1_kg"), ("1b Gate hold, off-peak gate demand only", "s1_offpeak_kg"),
                      ("2 Single-engine taxi", "s2_kg"), ("3 Ground power at stand", "s3_kg"), ("Combined 1 + 2 + 3", "combined_kg")]:
        rows.append({"scenario": name, "level": level, "tonnes_co2_saved": r[col] / 1000,
                     "pct_of_ground_co2": r[col] / base * 100,
                     "baseline_ground_kt": base / 1e6})
national = pd.DataFrame(rows).pivot(index="scenario", columns="level", values="tonnes_co2_saved")[["low", "central", "high"]]
pct = pd.DataFrame(rows).pivot(index="scenario", columns="level", values="pct_of_ground_co2")[["low", "central", "high"]]

central = scenario(pick("central"))
print(f"Baseline {YEAR}, 76 airports: taxi CO2 (taxi-out + taxi-in) {central['baseline_taxi_co2_kg'].sum() / 1e9:,.2f} Mt; "
      f"APU during turnarounds {central['apu_baseline_kg'].sum() / 1e9:,.2f} Mt (central assumptions)")
print("\\nTonnes CO2 saved per year:")
print(national.round(0).to_string())
print("\\n% of baseline ground CO2 (taxi + APU; the APU baseline changes with the low/central/high assumptions):")
print(pct.round(1).to_string())

spark.createDataFrame(national.reset_index()).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq3_national_savings")""")

code("""# Constraint checks: delay, capacity, turnaround and gate use
checks = pd.DataFrame([
    {"measure": "1 Gate hold", "departure delay (wheels-off)": "unchanged by design: queue time moves to the gate",
     "runway capacity": "unchanged: same take-off sequence and times",
     "turnaround": "unchanged for the held flight; gate occupied longer",
     "check in data": f"{central['gate_peak_share'].mean() * 100:.1f}% of departures are in hours when the airline has as many arrivals as departures (gate needed); variant 1b excludes them"},
    {"measure": "2 Single-engine taxi", "departure delay (wheels-off)": "unchanged: taxi times kept",
     "runway capacity": "unchanged", "turnaround": "unchanged",
     "check in data": "excluded in rain and at 3 deg C or below at the 10 weather airports; warm-up and cool-down minutes kept on two engines"},
    {"measure": "3 Ground power at stand", "departure delay (wheels-off)": "unchanged",
     "runway capacity": "unchanged", "turnaround": "unchanged: turn times measured from data, not shortened",
     "check in data": "needs ground power and pre-conditioned air at gates (investment, not an operational constraint)"},
])
print(checks.to_string(index=False))
print(turn_summary.to_string(index=False))""")

code("""# Per-airport results (central assumptions): savings per movement and share of taxi CO2
per_airport = central.copy()
per_airport["movements"] = per_airport["departures"] + per_airport["arrivals"]
for c in ["s1_kg", "s1_offpeak_kg", "s2_kg", "s3_kg", "combined_kg"]:
    per_airport[c.replace("_kg", "_kg_per_movement")] = per_airport[c] / per_airport["movements"]
per_airport["combined_pct_of_taxi_co2"] = (per_airport["s1_kg"] + per_airport["s2_out_after_hold_kg"] + per_airport["s2_in_kg"]) / per_airport["baseline_taxi_co2_kg"] * 100
per_airport = per_airport.reset_index().merge(spark.table("rq2_airport_ranking").select("airport", "adjusted_co2_kg_per_movement", "rank_adjusted").toPandas(), on="airport")

spark.createDataFrame(per_airport).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq3_airport_savings")

cols = ["airport", "movements", "s1_kg_per_movement", "s2_kg_per_movement", "s3_kg_per_movement", "combined_kg_per_movement", "combined_pct_of_taxi_co2", "rank_adjusted"]
print("Largest gate-hold savings per movement (central):")
print(per_airport.sort_values("s1_kg_per_movement", ascending=False)[cols].head(10).round(1).to_string(index=False))
print("\\nSpearman: gate-hold saving per movement vs RQ2 adjusted CO2 per movement:",
      round(per_airport["s1_kg_per_movement"].corr(per_airport["adjusted_co2_kg_per_movement"], method="spearman"), 3))""")

code("""# Sensitivity: change one assumption at a time from central to low and high (combined scenario, tonnes CO2 per year)
base_total = scenario(pick("central"))["combined_kg"].sum() / 1000
tornado = []
for key in list(A.keys()) + ["apu_fuel", "gpu_kw"]:
    vals = {}
    for level in ["low", "high"]:
        p = pick("central")
        i = 0 if level == "low" else 2
        if key == "apu_fuel":
            p["apu_fuel"] = {g: APU_FUEL_KG_MIN[g][i] for g in GROUPS}
        elif key == "gpu_kw":
            p["gpu_kw"] = {g: GPU_KW[g][i] for g in GROUPS}
        else:
            p[key] = A[key][i]
        vals[level] = scenario(p)["combined_kg"].sum() / 1000
    tornado.append({"assumption": key, "low": vals["low"], "high": vals["high"], "range": abs(vals["high"] - vals["low"])})
tornado = pd.DataFrame(tornado).sort_values("range")
spark.createDataFrame(tornado).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq3_sensitivity")

fig, ax = plt.subplots(figsize=(8, 4.5))
for i, r in enumerate(tornado.itertuples()):
    ax.barh(i, r.high - base_total, left=base_total)
    ax.barh(i, r.low - base_total, left=base_total)
ax.set_yticks(range(len(tornado)))
ax.set_yticklabels(tornado["assumption"])
ax.axvline(base_total, linestyle="--")
ax.set_xlabel("Combined CO2 saved per year (tonnes), one assumption at low or high")
ax.set_title(f"Sensitivity of combined savings (central = {base_total:,.0f} t)")
plt.tight_layout()
plt.show()
print(tornado.round(0).to_string(index=False))""")

nb = {
    "cells": cells,
    "metadata": {"application/vnd.databricks.v1+notebook": {"language": "python", "notebookName": "06_rq3_operational_scenarios"},
                 "language_info": {"name": "python"}},
    "nbformat": 4,
    "nbformat_minor": 0,
}
json.dump(nb, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
open(OUT, "a").write("\n")
print("written", OUT, len(cells), "cells")
