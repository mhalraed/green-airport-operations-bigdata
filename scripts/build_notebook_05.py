"""Builds notebooks/05_rq2_airport_comparison.ipynb (RQ2: airport ground carbon performance under comparable conditions)."""
import json

OUT = "notebooks/05_rq2_airport_comparison.ipynb"
cells = []


def md(t):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": t})


def code(t):
    cells.append({"cell_type": "code", "execution_count": 0, "metadata": {}, "outputs": [], "source": t})


md("""# RQ2: Which airports perform better under comparable conditions?

Research question 2: Which airports have better ground carbon performance under comparable conditions, and what are they doing differently?

Method
1. Taxi-out model on all departures from major U.S. airports (at least 50,000 departures in 2023-2025):
   taxi-out minutes = airport effect + airline + aircraft family + hour + month + weekday + year + departures and arrivals in the same airport-hour.
   The airport effect is the extra (or saved) taxi-out time at that airport compared with the network average, under the same conditions.
2. The same model for taxi-in at the arrival airport.
3. Airport effects are converted to kg CO2 per movement with one national average taxi fuel burn, so that fleet mix
   (an airline choice) does not drive the comparison.
4. The adjusted ranking is compared with the raw CO2 per movement and with the EM06DS green operations score.
5. Robustness: without the airline control, and with weather at the 10 weather airports.
6. Airport characteristics (runways, traffic per runway, peak intensity, hub concentration, regional-jet share) are related to the adjusted effects.""")

code("""# Imports and configuration
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.ml import Pipeline
from pyspark.ml.feature import StringIndexer, OneHotEncoder, VectorAssembler
from pyspark.ml.regression import LinearRegression

CATALOG = "new"
SCHEMA = "airgreenops"
spark.sql(f"USE CATALOG `{CATALOG}`")
spark.sql(f"USE SCHEMA `{SCHEMA}`")

ROOT = f"/Volumes/{CATALOG}/{SCHEMA}/project_data/airgreenops"
CO2_FACTOR = 3.16
MIN_DEPARTURES = 50_000
WEATHER_AIRPORTS = ["LAX", "SFO", "SEA", "LAS", "DEN", "ORD", "DFW", "ATL", "MIA", "JFK"]

gold = spark.table("gold_flight_emissions_clean")

# Major airports: at least MIN_DEPARTURES departures in 2023-2025
major = (
    gold.groupBy("origin").count()
    .where(F.col("count") >= MIN_DEPARTURES)
    .select(F.col("origin").alias("airport"))
)
MAJOR_AIRPORTS = sorted(r["airport"] for r in major.collect())
print("Major airports:", len(MAJOR_AIRPORTS))

# National average taxi fuel burn (kg/min) used to convert minutes to CO2 for every airport
NATIONAL_FUEL = gold.agg(F.avg("fuel_burn_kg_per_min")).first()[0]
print(f"National average taxi fuel burn: {NATIONAL_FUEL:.2f} kg/min")""")

code("""# Departure and arrival data sets with congestion at the airport in the same hour

# Departures and arrivals per airport, date and hour
deps_per_hour = gold.groupBy(F.col("origin").alias("airport"), "flight_date", F.col("scheduled_dep_hour").alias("hour")).agg(F.count("*").alias("deps_in_hour"))
arrs_per_hour = gold.groupBy(F.col("dest").alias("airport"), "flight_date", F.col("scheduled_arr_hour").alias("hour")).agg(F.count("*").alias("arrs_in_hour"))

departures = (
    gold
    .where(F.col("origin").isin(MAJOR_AIRPORTS) & F.col("taxi_out_clean").isNotNull())
    .select(F.col("origin").alias("airport"), "flight_date", F.col("scheduled_dep_hour").alias("hour"),
            "airline", "aircraft_family", "month", "day_of_week", "year",
            F.col("taxi_out_clean").alias("taxi_min"),
            "air_temperature", "wind_speed", "precipitation_1hr", "precipitation_1hr_missing")
    .join(deps_per_hour, ["airport", "flight_date", "hour"], "left")
    .join(arrs_per_hour, ["airport", "flight_date", "hour"], "left")
    .fillna({"deps_in_hour": 0, "arrs_in_hour": 0, "aircraft_family": "unknown"})
)

arrivals = (
    gold
    .where(F.col("dest").isin(MAJOR_AIRPORTS) & F.col("taxi_in_clean").isNotNull())
    .select(F.col("dest").alias("airport"), "flight_date", F.col("scheduled_arr_hour").alias("hour"),
            "airline", "aircraft_family", "month", "day_of_week", "year",
            F.col("taxi_in_clean").alias("taxi_min"))
    .join(deps_per_hour, ["airport", "flight_date", "hour"], "left")
    .join(arrs_per_hour, ["airport", "flight_date", "hour"], "left")
    .fillna({"deps_in_hour": 0, "arrs_in_hour": 0, "aircraft_family": "unknown"})
)

departures = departures.cache()
arrivals = arrivals.cache()
print("Departures:", departures.count(), "| Arrivals:", arrivals.count())""")

code("""# Airport effects from a fixed-effects linear regression (Spark, normal equations)
# Every airport gets its own dummy (no intercept), so each airport effect has a standard error.
# Effects are centred on the flight-weighted network average: 0 = average airport.

def airport_effects(df, cat_controls, num_controls, label):
    data = df
    for c in ["airport"] + cat_controls:
        data = data.withColumn(c, F.col(c).cast("string"))

    airport_indexer = StringIndexer(inputCol="airport", outputCol="airport_idx", stringOrderType="alphabetAsc")
    # No "keep" bucket: each control must drop a real reference category, otherwise the controls and the
    # airport dummies are perfectly collinear and the normal equations have no unique solution
    control_indexers = [StringIndexer(inputCol=c, outputCol=f"{c}_idx") for c in cat_controls]
    airport_ohe = OneHotEncoder(inputCols=["airport_idx"], outputCols=["airport_ohe"], dropLast=False)
    control_ohe = OneHotEncoder(inputCols=[f"{c}_idx" for c in cat_controls], outputCols=[f"{c}_ohe" for c in cat_controls], dropLast=True)
    assembler = VectorAssembler(inputCols=["airport_ohe"] + [f"{c}_ohe" for c in cat_controls] + num_controls, outputCol="features")
    lr = LinearRegression(featuresCol="features", labelCol="taxi_min", solver="normal", regParam=0.0, fitIntercept=False)

    model = Pipeline(stages=[airport_indexer] + control_indexers + [airport_ohe, control_ohe, assembler, lr]).fit(data)
    airports = model.stages[0].labels
    lr_model = model.stages[-1]
    n = len(airports)

    effects = pd.DataFrame({
        "airport": airports,
        "level_min": lr_model.coefficients.toArray()[:n],
        "se_min": lr_model.summary.coefficientStandardErrors[:n],
    })
    counts = data.groupBy("airport").count().toPandas()
    effects = effects.merge(counts, on="airport")
    weighted_mean = np.average(effects["level_min"], weights=effects["count"])
    effects["effect_min"] = effects["level_min"] - weighted_mean
    effects["ci_low"] = effects["effect_min"] - 1.96 * effects["se_min"]
    effects["ci_high"] = effects["effect_min"] + 1.96 * effects["se_min"]
    effects["spec"] = label
    # Spark reports R2 against zero when there is no intercept; report the usual (centred) R2 instead
    var_y = data.agg(F.var_pop("taxi_min")).first()[0]
    r2_centred = 1 - lr_model.summary.meanSquaredError / var_y
    print(f"{label}: {int(lr_model.summary.numInstances):,} flights, R2 (centred) = {r2_centred:.3f}")
    return effects[["spec", "airport", "count", "effect_min", "se_min", "ci_low", "ci_high"]]


CATS = ["airline", "aircraft_family", "hour", "month", "day_of_week", "year"]
NUMS = ["deps_in_hour", "arrs_in_hour"]

out_main = airport_effects(departures, CATS, NUMS, "taxi_out_main")
in_main = airport_effects(arrivals, CATS, NUMS, "taxi_in_main")
out_no_airline = airport_effects(departures, [c for c in CATS if c != "airline"], NUMS, "taxi_out_no_airline")
in_no_airline = airport_effects(arrivals, [c for c in CATS if c != "airline"], NUMS, "taxi_in_no_airline")

effects_all = pd.concat([out_main, in_main, out_no_airline, in_no_airline])
spark.createDataFrame(effects_all).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq2_airport_effects")""")

code("""# Adjusted ground CO2 per movement attributable to airport operations, and comparison with raw and EM06DS rankings

def adjusted(out_eff, in_eff, label):
    o = out_eff.set_index("airport")
    i = in_eff.set_index("airport")
    a = pd.DataFrame({"departures": o["count"], "arrivals": i["count"],
                      "taxi_out_effect_min": o["effect_min"], "taxi_in_effect_min": i["effect_min"],
                      "taxi_out_se": o["se_min"], "taxi_in_se": i["se_min"]}).dropna()
    w_out = a["departures"] / (a["departures"] + a["arrivals"])
    a["effect_min_per_movement"] = w_out * a["taxi_out_effect_min"] + (1 - w_out) * a["taxi_in_effect_min"]
    a["se_min_per_movement"] = np.sqrt((w_out * a["taxi_out_se"]) ** 2 + ((1 - w_out) * a["taxi_in_se"]) ** 2)
    a["adjusted_co2_kg_per_movement"] = a["effect_min_per_movement"] * NATIONAL_FUEL * CO2_FACTOR
    a["adjusted_ci_low"] = (a["effect_min_per_movement"] - 1.96 * a["se_min_per_movement"]) * NATIONAL_FUEL * CO2_FACTOR
    a["adjusted_ci_high"] = (a["effect_min_per_movement"] + 1.96 * a["se_min_per_movement"]) * NATIONAL_FUEL * CO2_FACTOR
    a["spec"] = label
    return a.reset_index().rename(columns={"index": "airport"})

main = adjusted(out_main, in_main, "main")
no_airline = adjusted(out_no_airline, in_no_airline, "no_airline")

raw = spark.table("gold_airport_ground_co2").select("airport", "co2_kg_per_movement", "movements").toPandas()
em06ds = (spark.table(f"`{CATALOG}`.airgreenops_em06ds.gold_airport_green_operations_score")
          .select(F.col("origin").alias("airport"), "green_operations_score").toPandas())

ranking = (main.merge(raw, on="airport", how="left").merge(em06ds, on="airport", how="left")
               .merge(no_airline[["airport", "adjusted_co2_kg_per_movement"]].rename(columns={"adjusted_co2_kg_per_movement": "adjusted_no_airline"}), on="airport"))

# Rank 1 = best (lowest CO2); EM06DS score: higher = greener
ranking["rank_adjusted"] = ranking["adjusted_co2_kg_per_movement"].rank()
ranking["rank_raw"] = ranking["co2_kg_per_movement"].rank()
ranking["rank_no_airline"] = ranking["adjusted_no_airline"].rank()
ranking["rank_em06ds"] = ranking["green_operations_score"].rank(ascending=False)
# Conventional OLS standard errors treat flights as independent; flights at the same airport on the same day share
# weather and runway conditions, so these intervals are likely too narrow. Year-to-year stability (below) is the main check.
ranking["ci_excludes_zero_conventional"] = (ranking["adjusted_ci_high"] < 0) | (ranking["adjusted_ci_low"] > 0)
ranking = ranking.sort_values("rank_adjusted")

spark.createDataFrame(ranking).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq2_airport_ranking")

def spearman(a, b):
    d = ranking[[a, b]].dropna()
    return round(d[a].corr(d[b], method="spearman"), 3), len(d)

print("Airports compared:", len(ranking))
print("Spearman rank correlation, adjusted vs raw CO2 per movement:", spearman("rank_adjusted", "rank_raw"))
print("Spearman rank correlation, adjusted vs adjusted without airline control:", spearman("rank_adjusted", "rank_no_airline"))
print("Spearman rank correlation, adjusted vs EM06DS green score:", spearman("rank_adjusted", "rank_em06ds"))
print("Airports whose conventional 95% CI excludes 0 (likely too narrow, see note):", int(ranking["ci_excludes_zero_conventional"].sum()))

cols = ["airport", "movements", "adjusted_co2_kg_per_movement", "adjusted_ci_low", "adjusted_ci_high",
        "taxi_out_effect_min", "taxi_in_effect_min", "co2_kg_per_movement", "rank_adjusted", "rank_raw", "rank_em06ds"]
print("\\nBest 10 (least extra ground CO2 under comparable conditions):")
print(ranking[cols].head(10).round(1).to_string(index=False))
print("\\nWorst 10:")
print(ranking[cols].tail(10).round(1).to_string(index=False))""")

code("""# Chart: adjusted effect with 95% confidence interval for every major airport
r = ranking.sort_values("adjusted_co2_kg_per_movement")
fig, ax = plt.subplots(figsize=(8, max(6, len(r) * 0.18)))
ax.errorbar(r["adjusted_co2_kg_per_movement"], range(len(r)),
            xerr=[r["adjusted_co2_kg_per_movement"] - r["adjusted_ci_low"], r["adjusted_ci_high"] - r["adjusted_co2_kg_per_movement"]],
            fmt="o", markersize=3, capsize=2)
ax.axvline(0, linestyle="--")
ax.set_yticks(range(len(r)))
ax.set_yticklabels(r["airport"], fontsize=7)
ax.set_xlabel("Extra ground CO2 per movement vs network average, comparable conditions (kg)")
ax.set_title("Airport ground operations performance (taxi-out + taxi-in)")
plt.tight_layout()
plt.show()

fig, ax = plt.subplots(figsize=(6, 5))
ax.scatter(ranking["rank_raw"], ranking["rank_adjusted"], s=12)
for _, row in ranking.iterrows():
    if abs(row["rank_raw"] - row["rank_adjusted"]) >= 15:
        ax.annotate(row["airport"], (row["rank_raw"], row["rank_adjusted"]), fontsize=7)
ax.plot([1, len(ranking)], [1, len(ranking)], linestyle="--")
ax.set_xlabel("Rank by raw CO2 per movement (1 = lowest)")
ax.set_ylabel("Rank after adjustment (1 = best)")
ax.set_title("How adjustment changes the ranking")
plt.tight_layout()
plt.show()""")

code("""# Robustness: add weather at the 10 weather airports and compare their taxi-out ranking
dep_weather = departures.where(F.col("airport").isin(WEATHER_AIRPORTS))
out_weather = airport_effects(dep_weather, CATS, NUMS + ["air_temperature", "wind_speed", "precipitation_1hr", "precipitation_1hr_missing"], "taxi_out_weather_10")
out_noweather_10 = airport_effects(dep_weather, CATS, NUMS, "taxi_out_noweather_10")

w = out_weather.set_index("airport")["effect_min"].rename("with_weather").to_frame().join(
    out_noweather_10.set_index("airport")["effect_min"].rename("without_weather"))
w["rank_with"] = w["with_weather"].rank()
w["rank_without"] = w["without_weather"].rank()
print("10 weather airports, taxi-out effect (min) with and without weather controls:")
print(w.round(2).sort_values("with_weather").to_string())
print("Spearman rank correlation:", round(w["rank_with"].corr(w["rank_without"], method="spearman"), 3))""")

code("""# Robustness: is each airport's performance stable from year to year?
# Re-estimate the main taxi-out and taxi-in models separately for 2023, 2024 and 2025
CATS_NO_YEAR = [c for c in CATS if c != "year"]
by_year = []
for yr in [2023, 2024, 2025]:
    o = airport_effects(departures.where(F.col("year") == yr), CATS_NO_YEAR, NUMS, f"taxi_out_{yr}")
    i = airport_effects(arrivals.where(F.col("year") == yr), CATS_NO_YEAR, NUMS, f"taxi_in_{yr}")
    a = adjusted(o, i, str(yr))[["airport", "adjusted_co2_kg_per_movement"]].rename(columns={"adjusted_co2_kg_per_movement": f"adj_{yr}"})
    by_year.append(a.set_index("airport"))

years = pd.concat(by_year, axis=1).dropna()
spark.createDataFrame(years.reset_index()).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq2_airport_effects_by_year")

for a, b in [("adj_2023", "adj_2024"), ("adj_2024", "adj_2025"), ("adj_2023", "adj_2025")]:
    print(f"Spearman {a} vs {b}: {years[a].corr(years[b], method='spearman'):.3f}")
same_side = ((years > 0).all(axis=1) | (years < 0).all(axis=1))
print(f"Airports on the same side of the average in all three years: {int(same_side.sum())} of {len(years)}")
print(years.round(1).sort_values("adj_2025").to_string())""")

code("""# What are the better airports doing differently? Airport characteristics vs adjusted performance

# Runways from OurAirports (open, paved length at least 5,000 ft)
airports_csv = spark.read.option("header", "true").csv(f"{ROOT}/raw/airports/airports.csv").select("ident", "iata_code")
runways_csv = spark.read.option("header", "true").csv(f"{ROOT}/raw/airports/runways.csv")
runways = (
    runways_csv
    .where((F.col("closed") == "0") & (F.col("length_ft").cast("int") >= 5000))
    .join(airports_csv, runways_csv["airport_ident"] == airports_csv["ident"])
    .groupBy(F.col("iata_code").alias("airport"))
    .agg(F.count("*").alias("runways"), F.max(F.col("length_ft").cast("int")).alias("longest_runway_ft"))
)

dep_flights = gold.where(F.col("origin").isin(MAJOR_AIRPORTS))
traits = (
    dep_flights.groupBy(F.col("origin").alias("airport"))
    .agg(F.count("*").alias("departures_3y"),
         F.avg(F.when(F.col("aircraft_group") == "regional_jet", 1).otherwise(0)).alias("regional_jet_share"),
         F.avg("airport_hour_departure_count").alias("avg_departures_in_hour"))
    .join(
        dep_flights.groupBy(F.col("origin").alias("airport"), "airline").count()
        .withColumn("share", F.col("count") / F.sum("count").over(Window.partitionBy("airport")))
        .groupBy("airport").agg(F.max("share").alias("top_airline_share")),
        "airport")
    .join(runways, "airport", "left")
    .toPandas()
)
traits["departures_per_runway_per_day"] = traits["departures_3y"] / 1096 / traits["runways"]

profile = ranking[["airport", "adjusted_co2_kg_per_movement", "taxi_out_effect_min", "taxi_in_effect_min"]].merge(traits, on="airport")
spark.createDataFrame(profile).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq2_airport_profile")

features = ["runways", "departures_per_runway_per_day", "avg_departures_in_hour", "top_airline_share", "regional_jet_share", "longest_runway_ft"]
corr = pd.DataFrame({
    "characteristic": features,
    "spearman_with_adjusted_co2": [round(profile["adjusted_co2_kg_per_movement"].corr(profile[f], method="spearman"), 3) for f in features],
    "airports": [int(profile[[f, "adjusted_co2_kg_per_movement"]].dropna().shape[0]) for f in features],
})
print(corr.to_string(index=False))

best = profile.nsmallest(10, "adjusted_co2_kg_per_movement")
worst = profile.nlargest(10, "adjusted_co2_kg_per_movement")
print("\\nMedian characteristics, best 10 vs worst 10 airports:")
print(pd.DataFrame({"best_10": best[features].median(), "worst_10": worst[features].median()}).round(2).to_string())""")

nb = {
    "cells": cells,
    "metadata": {"application/vnd.databricks.v1+notebook": {"language": "python", "notebookName": "05_rq2_airport_comparison"},
                 "language_info": {"name": "python"}},
    "nbformat": 4,
    "nbformat_minor": 0,
}
json.dump(nb, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
open(OUT, "a").write("\n")
print("written", OUT, len(cells), "cells")
