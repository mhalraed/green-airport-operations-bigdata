import json, uuid

OUT = "notebooks/04_rq1_taxi_time_drivers.ipynb"

cells = []


def md(t):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": t})


def code(t):
    cells.append({"cell_type": "code", "execution_count": 0, "metadata": {}, "outputs": [], "source": t})


md("""# RQ1: What drives taxi time and ground CO2?

Research question 1: How do aircraft type, fuel use, operating weight, taxi time, weather and congestion influence ground emissions?

Ground CO2 per flight = taxi minutes x taxi fuel burn (kg/min, from aircraft type and ICAO engine data) x 3.16.
Fuel burn per minute is fixed by the aircraft and engine, so the part that varies with operations is taxi time.
This notebook models taxi-out time at the 10 airports with complete weather data and measures how much each factor adds.

Data: `gold_flight_emissions_clean` (notebook 01). Split by time: train Jan 2023 - Sep 2024, validation Oct - Dec 2024, test 2025.""")

code("""# Imports and configuration
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pyspark.sql import functions as F
from pyspark.ml import Pipeline
from pyspark.ml.feature import StringIndexer, OneHotEncoder, VectorAssembler
from pyspark.ml.regression import LinearRegression

CATALOG = "new"
SCHEMA = "airgreenops"
spark.sql(f"USE CATALOG `{CATALOG}`")
spark.sql(f"USE SCHEMA `{SCHEMA}`")

SEED = 42
CO2_FACTOR = 3.16
TRAIN_SAMPLE_ROWS = 2_000_000

# Airports with an hourly weather station (notebook 01)
WEATHER_AIRPORTS = ["LAX", "SFO", "SEA", "LAS", "DEN", "ORD", "DFW", "ATL", "MIA", "JFK"]

CATEGORICAL = ["origin", "airline", "aircraft_family", "aircraft_group", "scheduled_dep_hour", "day_of_week", "month"]
NUMERIC = [
    "airport_hour_departure_count",
    "origin_hour_arrival_count",
    "air_temperature",
    "wind_speed",
    "precipitation_1hr",
    "precipitation_1hr_missing",
]
TARGET = "taxi_out_clean"
print("Configuration ready")""")

code("""# Build the modelling table for the 10 weather airports

gold = spark.table("gold_flight_emissions_clean")

# Arrivals landing at the departure airport in the same hour (runway and taxiway traffic from landings)
arrivals_at_origin = (
    gold
    .groupBy(
        F.col("dest").alias("origin"),
        "flight_date",
        F.col("scheduled_arr_hour").alias("scheduled_dep_hour")
    )
    .agg(F.count("*").alias("origin_hour_arrival_count"))
)

model_data = (
    gold
    .where(F.col("origin").isin(WEATHER_AIRPORTS))
    .where(F.col(TARGET).isNotNull())
    .join(arrivals_at_origin, ["origin", "flight_date", "scheduled_dep_hour"], "left")
    .fillna({"origin_hour_arrival_count": 0, "aircraft_family": "unknown"})
    .withColumn(
        "set",
        F.when(F.col("year") == 2025, "test")
         .when((F.col("year") == 2024) & (F.col("month") >= 10), "val")
         .otherwise("train")
    )
    .select(
        "set", "year", "flight_date",
        *CATEGORICAL,
        *NUMERIC,
        "fuel_burn_kg_per_min",
        TARGET
    )
)

model_data.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq1_model_data")
model_data = spark.table("rq1_model_data")

display(model_data.groupBy("set").agg(F.count("*").alias("flights"), F.round(F.avg(TARGET), 2).alias("mean_taxi_out_min")).orderBy("set"))""")

md("""## 1. Descriptive evidence

Mean taxi-out time by congestion, rain, wind and aircraft class, before any model.""")

code("""# Mean taxi-out by departure congestion band, rain, wind band and aircraft class
desc = model_data.where(F.col("set") != "test")

by_congestion = (
    desc
    .withColumn("dep_count_band", F.least(F.floor(F.col("airport_hour_departure_count") / 10) * 10, F.lit(120)))
    .groupBy("dep_count_band")
    .agg(F.round(F.avg(TARGET), 2).alias("mean_taxi_out"), F.count("*").alias("flights"))
    .orderBy("dep_count_band")
    .toPandas()
)

by_weather = (
    desc
    .withColumn("rain", F.when(F.col("precipitation_1hr_missing") == 1, "unknown").when(F.col("precipitation_1hr") > 0, "rain").otherwise("dry"))
    .withColumn("wind_band", F.when(F.col("wind_speed") < 5, "<5 m/s").when(F.col("wind_speed") < 10, "5-10 m/s").otherwise(">=10 m/s"))
    .groupBy("rain", "wind_band")
    .agg(F.round(F.avg(TARGET), 2).alias("mean_taxi_out"), F.count("*").alias("flights"))
    .orderBy("rain", "wind_band")
    .toPandas()
)

by_class = (
    desc.groupBy("aircraft_group")
    .agg(F.round(F.avg(TARGET), 2).alias("mean_taxi_out"), F.round(F.avg("fuel_burn_kg_per_min"), 2).alias("fuel_kg_per_min"), F.count("*").alias("flights"))
    .orderBy("aircraft_group")
    .toPandas()
)

fig, axes = plt.subplots(1, 2, figsize=(13, 4))
axes[0].plot(by_congestion["dep_count_band"], by_congestion["mean_taxi_out"], marker="o")
axes[0].set_xlabel("Departures in the same airport-hour (band of 10; 120 = 120 or more)")
axes[0].set_ylabel("Mean taxi-out (min)")
axes[0].set_title("Taxi-out vs departure congestion")
pivot = by_weather.pivot(index="wind_band", columns="rain", values="mean_taxi_out").reindex(["<5 m/s", "5-10 m/s", ">=10 m/s"])
pivot.plot(kind="bar", ax=axes[1])
axes[1].set_ylabel("Mean taxi-out (min)")
axes[1].set_title("Taxi-out by rain and wind")
plt.tight_layout()
plt.show()

print(by_congestion.to_string(index=False))
print(by_weather.to_string(index=False))
print(by_class.to_string(index=False))""")

md("""## 2. Predictive models on the 2025 test set

All models use the same features, known before pushback. Training sample: 2M flights from Jan 2023 - Sep 2024
(the linear regression uses the full training set in Spark). Validation (Oct - Dec 2024) is used for early stopping only.""")

code("""# Training sample, validation and test sets as pandas data frames
train_count = model_data.where(F.col("set") == "train").count()
fraction = min(1.0, TRAIN_SAMPLE_ROWS / train_count)

cols = CATEGORICAL + NUMERIC + ["fuel_burn_kg_per_min", TARGET]
train_pd = model_data.where(F.col("set") == "train").sample(False, fraction, seed=SEED).select(cols).toPandas()
val_pd = model_data.where(F.col("set") == "val").select(cols).toPandas()
test_pd = model_data.where(F.col("set") == "test").select(cols + ["flight_date"]).toPandas()

for d in (train_pd, val_pd, test_pd):
    for c in CATEGORICAL:
        d[c] = d[c].astype(str)

print(f"Train sample: {len(train_pd):,} of {train_count:,} | Validation: {len(val_pd):,} | Test (2025): {len(test_pd):,}")
predictions = {}""")

code("""# Model 1: historical average (what an airport would assume without a model)
# Mean taxi-out per airport, hour and month in the training period; airport mean as fallback
hist_keys = ["origin", "scheduled_dep_hour", "month"]
hist = train_pd.groupby(hist_keys)[TARGET].mean().rename("hist_mean").reset_index()
airport_mean = train_pd.groupby("origin")[TARGET].mean().rename("airport_mean").reset_index()

p = test_pd[hist_keys].merge(hist, on=hist_keys, how="left").merge(airport_mean, on="origin", how="left")
predictions["historical_average"] = p["hist_mean"].fillna(p["airport_mean"]).to_numpy()
print("Historical average ready")""")

code("""# Model 2: linear regression in Spark on the full training set
indexers = [StringIndexer(inputCol=c, outputCol=f"{c}_idx", handleInvalid="keep") for c in CATEGORICAL]
encoder = OneHotEncoder(inputCols=[f"{c}_idx" for c in CATEGORICAL], outputCols=[f"{c}_ohe" for c in CATEGORICAL])
assembler = VectorAssembler(inputCols=[f"{c}_ohe" for c in CATEGORICAL] + NUMERIC, outputCol="features", handleInvalid="keep")
lr = LinearRegression(featuresCol="features", labelCol=TARGET, regParam=0.0)

spark_data = model_data
for c in CATEGORICAL:
    spark_data = spark_data.withColumn(c, F.col(c).cast("string"))

start = time.time()
lr_model = Pipeline(stages=indexers + [encoder, assembler, lr]).fit(spark_data.where(F.col("set") == "train"))
print(f"Linear regression trained on {train_count:,} flights in {time.time() - start:.0f} s")

lr_test = lr_model.transform(spark_data.where(F.col("set") == "test")).select("prediction", TARGET, "flight_date", "origin").toPandas()
# The Spark predictions come back in their own row order, so this model is scored on its own frame
lr_eval = lr_test""")

code("""# Model 3: gradient-boosted trees (LightGBM) with early stopping on the validation period
import lightgbm as lgb

def to_lgb(d):
    X = d[CATEGORICAL + NUMERIC].copy()
    for c in CATEGORICAL:
        X[c] = X[c].astype("category")
    return X

X_train, X_val, X_test = to_lgb(train_pd), to_lgb(val_pd), to_lgb(test_pd)
for c in CATEGORICAL:
    cats = X_train[c].cat.categories
    X_val[c] = X_val[c].cat.set_categories(cats)
    X_test[c] = X_test[c].cat.set_categories(cats)

start = time.time()
gbm = lgb.LGBMRegressor(n_estimators=2000, learning_rate=0.05, num_leaves=127, min_child_samples=200,
                        subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=SEED, verbose=-1)
gbm.fit(X_train, train_pd[TARGET], eval_set=[(X_val, val_pd[TARGET])], eval_metric="l1",
        callbacks=[lgb.early_stopping(50, verbose=False)])
print(f"LightGBM: {gbm.best_iteration_} trees, trained in {time.time() - start:.0f} s")
predictions["gradient_boosted_trees"] = gbm.predict(X_test, num_iteration=gbm.best_iteration_)""")

code("""# Model 4: neural network (multilayer perceptron)
# Trained one epoch at a time; early stopping uses the same later period as LightGBM (Oct - Dec 2024),
# so the network stops when it no longer improves on months it has not seen.
import copy
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder as SkOneHot, StandardScaler
from sklearn.neural_network import MLPRegressor

prep = ColumnTransformer([
    ("cat", SkOneHot(handle_unknown="ignore"), CATEGORICAL),
    ("num", StandardScaler(), NUMERIC),
])
X_train_nn = prep.fit_transform(train_pd[CATEGORICAL + NUMERIC])
X_val_nn = prep.transform(val_pd[CATEGORICAL + NUMERIC])
X_test_nn = prep.transform(test_pd[CATEGORICAL + NUMERIC])
y_train, y_val = train_pd[TARGET].to_numpy(), val_pd[TARGET].to_numpy()

net = MLPRegressor(hidden_layer_sizes=(128, 64), activation="relu", solver="adam", alpha=1e-4,
                   batch_size=1024, learning_rate_init=1e-3, random_state=SEED)

best_val_mae, best_net, epochs_without_gain, val_curve = np.inf, None, 0, []
start = time.time()
for epoch in range(1, 51):
    net.partial_fit(X_train_nn, y_train)
    val_mae = np.abs(y_val - net.predict(X_val_nn)).mean()
    val_curve.append(val_mae)
    if val_mae < best_val_mae - 0.001:
        best_val_mae, best_net, epochs_without_gain = val_mae, copy.deepcopy(net), 0
    else:
        epochs_without_gain += 1
        if epochs_without_gain >= 3:
            break

best_epoch = int(np.argmin(val_curve)) + 1
print(f"MLP: {len(val_curve)} epochs run, best epoch {best_epoch}, validation MAE {best_val_mae:.3f} min, {time.time() - start:.0f} s")
predictions["mlp_neural_network"] = best_net.predict(X_test_nn)

plt.figure(figsize=(6, 3.5))
plt.plot(range(1, len(val_curve) + 1), val_curve, marker="o")
plt.axvline(best_epoch, linestyle="--")
plt.xlabel("Epoch")
plt.ylabel("Validation MAE (min), Oct-Dec 2024")
plt.title("MLP learning curve and early stopping")
plt.tight_layout()
plt.show()""")

code("""# Compare all models on the 2025 test set: MAE, RMSE, R2 with bootstrap 95% confidence intervals for MAE
rng = np.random.default_rng(SEED)

def metrics(y, yhat, n_boot=100):
    err = np.abs(y - yhat)
    mae = err.mean()
    rmse = np.sqrt(((y - yhat) ** 2).mean())
    r2 = 1 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    boots = [err[rng.integers(0, len(err), len(err))].mean() for _ in range(n_boot)]
    return mae, np.percentile(boots, 2.5), np.percentile(boots, 97.5), rmse, r2

y_test = test_pd[TARGET].to_numpy()
rows = []
for name, yhat in predictions.items():
    mae, lo, hi, rmse, r2 = metrics(y_test, yhat)
    rows.append({"model": name, "mae_min": mae, "mae_ci_low": lo, "mae_ci_high": hi, "rmse_min": rmse, "r2": r2})

mae, lo, hi, rmse, r2 = metrics(lr_eval[TARGET].to_numpy(), lr_eval["prediction"].to_numpy())
rows.append({"model": "linear_regression", "mae_min": mae, "mae_ci_low": lo, "mae_ci_high": hi, "rmse_min": rmse, "r2": r2})

comparison = pd.DataFrame(rows).sort_values("mae_min")
spark.createDataFrame(comparison).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq1_model_comparison")
print("Test set: 2025 flights at the 10 weather airports,", f"{len(y_test):,}", "flights; mean taxi-out", round(y_test.mean(), 2), "min")
print(comparison.round(3).to_string(index=False))

# MAE by airport for the best model
best = comparison.iloc[0]["model"]
if best in predictions:
    by_airport = (test_pd.assign(abs_err=np.abs(y_test - predictions[best]))
                  .groupby("origin").agg(flights=("abs_err", "size"), mae_min=("abs_err", "mean"), mean_taxi_out=(TARGET, "mean")).round(2))
    print("MAE by airport for", best)
    print(by_airport.to_string())""")

md("""## 3. What drives taxi time? (SHAP values from the gradient-boosted trees)""")

code("""# SHAP values on a 20,000-flight sample of the 2025 test set
import shap

shap_sample = X_test.sample(20_000, random_state=SEED)
explainer = shap.TreeExplainer(gbm)
shap_values = explainer.shap_values(shap_sample)

importance = (pd.DataFrame({"feature": shap_sample.columns, "mean_abs_shap_min": np.abs(shap_values).mean(axis=0)})
              .sort_values("mean_abs_shap_min", ascending=False))
spark.createDataFrame(importance).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq1_shap_importance")
print(importance.round(3).to_string(index=False))

shap.summary_plot(shap_values, shap_sample, show=False, max_display=13)
plt.title("SHAP: contribution to predicted taxi-out (minutes)")
plt.tight_layout()
plt.show()

for feature in ["airport_hour_departure_count", "origin_hour_arrival_count", "precipitation_1hr", "wind_speed"]:
    shap.dependence_plot(feature, shap_values, shap_sample, interaction_index=None, show=False)
    plt.title(f"SHAP dependence: {feature}")
    plt.tight_layout()
    plt.show()""")

md("""## 4. Effect sizes in minutes and kg CO2 (regression with airport, hour, month and weekday fixed effects)""")

code("""# Ordinary least squares on 1M training flights, heteroskedasticity-robust (HC1) standard errors
import statsmodels.formula.api as smf

ols_pd = train_pd.sample(1_000_000, random_state=SEED) if len(train_pd) > 1_000_000 else train_pd.copy()
ols_pd["rain"] = ((ols_pd["precipitation_1hr"] > 0) & (ols_pd["precipitation_1hr_missing"] == 0)).astype(int)
ols_pd["deps_10"] = ols_pd["airport_hour_departure_count"] / 10
ols_pd["arrs_10"] = ols_pd["origin_hour_arrival_count"] / 10

formula = ("taxi_out_clean ~ deps_10 + arrs_10 + rain + wind_speed + air_temperature + "
           "C(aircraft_group) + C(origin) + C(scheduled_dep_hour) + C(month) + C(day_of_week)")
ols = smf.ols(formula, data=ols_pd).fit(cov_type="HC1")

keep = ["deps_10", "arrs_10", "rain", "wind_speed", "air_temperature"] + [p for p in ols.params.index if p.startswith("C(aircraft_group)")]
effects = pd.DataFrame({"term": keep, "minutes": ols.params[keep].values,
                        "ci_low": ols.conf_int().loc[keep, 0].values, "ci_high": ols.conf_int().loc[keep, 1].values})

# Convert minutes to kg CO2 at the average taxi fuel burn of the training flights
mean_fuel = train_pd["fuel_burn_kg_per_min"].mean()
effects["kg_co2_per_flight"] = effects["minutes"] * mean_fuel * CO2_FACTOR
spark.createDataFrame(effects).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("rq1_effect_sizes")

print(f"R2 = {ols.rsquared:.3f} on {int(ols.nobs):,} flights; mean taxi fuel burn {mean_fuel:.2f} kg/min")
print("deps_10 / arrs_10 = effect of 10 more departures / arrivals in the same airport-hour")
print(effects.round(3).to_string(index=False))""")

nb = {
    "cells": cells,
    "metadata": {"application/vnd.databricks.v1+notebook": {"language": "python", "notebookName": "04_rq1_taxi_time_drivers"},
                 "language_info": {"name": "python"}},
    "nbformat": 4,
    "nbformat_minor": 0,
}
json.dump(nb, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
open(OUT, "a").write("\n")
print("written", OUT, len(cells), "cells")
