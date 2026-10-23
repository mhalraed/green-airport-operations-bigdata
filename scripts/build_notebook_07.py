"""Builds notebooks/07_spark_scaling_benchmark.ipynb (Spark scaling: data volume x cluster size)."""
import json

OUT = "notebooks/07_spark_scaling_benchmark.ipynb"
cells = []


def md(t):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": t})


def code(t):
    cells.append({"cell_type": "code", "execution_count": 0, "metadata": {}, "outputs": [], "source": t})


md("""# Spark scaling benchmark

Two representative workloads from the thesis pipeline are timed on 25%, 50% and 100% of the 2023-2025 departures:
1. **Congestion and aggregation (Spark SQL)**: departures and arrivals per airport-hour, joined back to every flight, then
   airport-level aggregates (shuffle-heavy, as in notebooks 01 and 05).
2. **Fixed-effects regression (Spark MLlib)**: the RQ2 taxi-out model with airport, airline, aircraft family and time dummies
   solved with the normal equations (notebook 05).

The notebook is run once per cluster size (1, 2 and 4 workers); each run appends its timings to `scaling_benchmark`.""")

code("""# Configuration
import time
import pandas as pd
import matplotlib.pyplot as plt

from pyspark.sql import functions as F
from pyspark.ml import Pipeline
from pyspark.ml.feature import StringIndexer, OneHotEncoder, VectorAssembler
from pyspark.ml.regression import LinearRegression

spark.sql("USE CATALOG `new`")
spark.sql("USE SCHEMA `airgreenops`")

workers = sc._jsc.sc().getExecutorMemoryStatus().size() - 1
cores = sc.defaultParallelism
print("Workers:", workers, "| total cores:", cores)

major = [r["airport"] for r in spark.table("rq2_airport_ranking").select("airport").collect()]
base = (spark.table("gold_flight_emissions_clean")
        .where(F.col("origin").isin(major) & F.col("taxi_out_clean").isNotNull())
        .select("origin", "dest", "flight_date", "scheduled_dep_hour", "scheduled_arr_hour", "airline",
                "aircraft_family", "month", "day_of_week", "year", "taxi_out_clean"))
print("Flights at 100%:", base.count())""")

code("""# Workloads

def workload_sql(df):
    deps = df.groupBy("origin", "flight_date", "scheduled_dep_hour").agg(F.count("*").alias("deps_in_hour"))
    arrs = (df.groupBy(F.col("dest").alias("origin"), "flight_date", F.col("scheduled_arr_hour").alias("scheduled_dep_hour"))
              .agg(F.count("*").alias("arrs_in_hour")))
    out = (df.join(deps, ["origin", "flight_date", "scheduled_dep_hour"], "left")
             .join(arrs, ["origin", "flight_date", "scheduled_dep_hour"], "left")
             .groupBy("origin", "aircraft_family")
             .agg(F.avg("taxi_out_clean").alias("mean_taxi"), F.avg("deps_in_hour").alias("mean_deps"),
                  F.expr("percentile_approx(taxi_out_clean, 0.2)").alias("p20_taxi")))
    return out.count()


def workload_mllib(df):
    data = df.fillna({"aircraft_family": "unknown"})
    cats = ["airline", "aircraft_family", "scheduled_dep_hour", "month", "day_of_week", "year"]
    for c in ["origin"] + cats:
        data = data.withColumn(c, F.col(c).cast("string"))
    stages = [StringIndexer(inputCol="origin", outputCol="origin_idx")]
    stages += [StringIndexer(inputCol=c, outputCol=f"{c}_idx") for c in cats]
    stages += [OneHotEncoder(inputCols=["origin_idx"], outputCols=["origin_ohe"], dropLast=False),
               OneHotEncoder(inputCols=[f"{c}_idx" for c in cats], outputCols=[f"{c}_ohe" for c in cats], dropLast=True),
               VectorAssembler(inputCols=["origin_ohe"] + [f"{c}_ohe" for c in cats], outputCol="features"),
               LinearRegression(featuresCol="features", labelCol="taxi_out_clean", solver="normal", regParam=0.0, fitIntercept=False)]
    return Pipeline(stages=stages).fit(data).stages[-1].summary.numInstances

print("Workloads defined")""")

code("""# Time each workload on 25%, 50% and 100% of the data (data cached before timing, so I/O from cloud storage is excluded)
rows = []
for fraction in [0.25, 0.5, 1.0]:
    df = (base if fraction == 1.0 else base.sample(False, fraction, seed=42)).cache()
    n = df.count()
    for name, fn in [("sql_congestion_aggregation", workload_sql), ("mllib_fixed_effects_regression", workload_mllib)]:
        start = time.time()
        fn(df)
        seconds = time.time() - start
        rows.append({"workers": workers, "cores": cores, "fraction": fraction, "flights": n, "workload": name, "seconds": round(seconds, 1)})
        print(f"workers={workers} fraction={fraction:.2f} flights={n:,} {name}: {seconds:.1f} s")
    df.unpersist()

result = pd.DataFrame(rows)
result["run_at"] = pd.Timestamp.utcnow().isoformat()
spark.createDataFrame(result).write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable("scaling_benchmark")""")

code("""# Summary across all runs so far (one run per cluster size)
bench = spark.table("scaling_benchmark").toPandas()
latest = bench.sort_values("run_at").groupby(["workers", "fraction", "workload"]).tail(1)
print(latest.pivot_table(index=["workload", "fraction"], columns="workers", values="seconds").to_string())

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
for ax, wl in zip(axes, sorted(latest["workload"].unique())):
    d = latest[latest["workload"] == wl]
    for w, g in d.groupby("workers"):
        ax.plot(g["flights"] / 1e6, g["seconds"], marker="o", label=f"{w} worker(s)")
    ax.set_xlabel("Flights (millions)")
    ax.set_ylabel("Seconds")
    ax.set_title(wl)
    ax.legend()
plt.tight_layout()
plt.show()""")

nb = {
    "cells": cells,
    "metadata": {"application/vnd.databricks.v1+notebook": {"language": "python", "notebookName": "07_spark_scaling_benchmark"},
                 "language_info": {"name": "python"}},
    "nbformat": 4,
    "nbformat_minor": 0,
}
json.dump(nb, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
open(OUT, "a").write("\n")
print("written", OUT, len(cells), "cells")
