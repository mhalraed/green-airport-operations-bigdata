"""Builds notebooks/08_figures_tables.ipynb (Databricks) and colab/figures_tables_colab.ipynb (Google Colab): thesis figures
(PNG) and tables (CSV) from the result tables, plus a VIF check. Both share every cell except the data connection."""
import json
import os

import colab_common as colab

OUT = "notebooks/08_figures_tables.ipynb"
OUT_COLAB = "colab/figures_tables_colab.ipynb"
cells = []


def md(t):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": t})


def code(t):
    cells.append({"cell_type": "code", "execution_count": 0, "metadata": {}, "outputs": [], "source": t})


code("""# Plotting style and helpers (the same on Databricks and Colab)
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

os.makedirs(OUT_DIR, exist_ok=True)
WEATHER_AIRPORTS = ["LAX", "SFO", "SEA", "LAS", "DEN", "ORD", "DFW", "ATL", "MIA", "JFK"]

plt.rcParams.update({"figure.dpi": 110, "savefig.dpi": 300, "font.size": 10, "axes.titlesize": 11,
                     "axes.spines.top": False, "axes.spines.right": False})
# Colour-blind-safe pair (validated): blue = main series, orange = second series; grey = reference / before
BLUE, ORANGE, GREY, RED = "#2a78d6", "#eb6834", "#9aa5b1", "#e34948"
index = []

def save_fig(fig, number, title, source):
    name = f"figure_{number:02d}.png"
    fig.savefig(f"{OUT_DIR}/{name}", bbox_inches="tight")
    plt.close(fig)
    index.append({"item": f"Figure {number}", "file": name, "title": title, "source": source})
    print("saved", name, "-", title)

def save_table(df, number, title, source):
    name = f"table_{number:02d}.csv"
    df.to_csv(f"{OUT_DIR}/{name}", index=False)
    index.append({"item": f"Table {number}", "file": name, "title": title, "source": source})
    print("saved", name, "-", title)""")

code("""# Figure 1: records through the pipeline
n = sql('''SELECT (SELECT count(*) FROM bronze_bts_flights) AS bronze, (SELECT count(*) FROM silver_flights) AS silver,
                  (SELECT count(*) FROM gold_flight_emissions_clean) AS gold''').iloc[0]
counts = {"Bronze: BTS raw records": int(n["bronze"]), "Silver: cleaned flights": int(n["silver"]),
          "Gold: flights with emission estimates": int(n["gold"])}
fig, ax = plt.subplots(figsize=(7, 2.6))
ax.barh(list(counts.keys())[::-1], [v / 1e6 for v in counts.values()][::-1], color=BLUE)
for i, v in enumerate(list(counts.values())[::-1]):
    ax.text(v / 1e6, i, f" {v:,}", va="center", fontsize=9)
ax.set_xlabel("Records (millions)")
ax.set_xlim(0, max(counts.values()) / 1e6 * 1.25)
ax.set_title("Records through the Bronze, Silver and Gold layers (2023-2025)")
save_fig(fig, 1, "Records through the Bronze, Silver and Gold layers", "notebook 01")""")

code("""# Figure 2: weather alignment check, warmest local departure hour (season-adjusted) before and after the UTC fix
def warmest(table):
    return sql(f'''
        WITH f AS (SELECT origin, scheduled_dep_hour,
                          air_temperature - avg(air_temperature) OVER (PARTITION BY origin, flight_date) AS anom
                   FROM {table} WHERE origin IN ({",".join("'" + a + "'" for a in WEATHER_AIRPORTS)}) AND air_temperature IS NOT NULL),
             h AS (SELECT origin, scheduled_dep_hour, avg(anom) a FROM f GROUP BY origin, scheduled_dep_hour HAVING count(*) >= 2000)
        SELECT origin, scheduled_dep_hour FROM (
          SELECT *, row_number() OVER (PARTITION BY origin ORDER BY a DESC) rn FROM h) WHERE rn = 1''')

before = warmest("`new`.airgreenops_em06ds.silver_flight_weather_features").rename(columns={"scheduled_dep_hour": "EM06DS (local hour joined to UTC)"})
after = warmest("silver_flight_weather_features").rename(columns={"scheduled_dep_hour": "Thesis (UTC-aligned)"})
w = before.merge(after, on="origin").sort_values("origin")
fig, ax = plt.subplots(figsize=(7, 3.2))
x = np.arange(len(w))
ax.bar(x - 0.2, w["EM06DS (local hour joined to UTC)"], 0.4, color=GREY, label="EM06DS (local hour joined to UTC)")
ax.bar(x + 0.2, w["Thesis (UTC-aligned)"], 0.4, color=BLUE, label="Thesis (UTC-aligned)")
ax.set_xticks(x)
ax.set_xticklabels(w["origin"])
ax.set_ylabel("Warmest local departure hour")
ax.set_ylim(0, 24)
ax.set_yticks([0, 6, 12, 18, 24])
ax.legend(frameon=False, fontsize=8, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2)
ax.set_title("Weather alignment check: hour with the highest temperature anomaly", pad=24)
save_fig(fig, 2, "Weather alignment check before and after the UTC correction", "notebook 01 (B1); frozen EM06DS tables")""")

code("""# Figure 3: taxi-out by rain, wind and congestion (RQ1 descriptive, Jan 2023 - Dec 2024, 10 weather airports)
by_cong = sql('''SELECT least(floor(airport_hour_departure_count / 10) * 10, 90) AS band, avg(taxi_out_clean) AS m, count(*) AS n
                 FROM rq1_model_data WHERE `set` != 'test' GROUP BY 1 ORDER BY 1''')
by_wx = (sql('''SELECT CASE WHEN precipitation_1hr > 0 THEN 'Rain' ELSE 'Dry' END AS rain,
                       CASE WHEN wind_speed < 5 THEN '<5' WHEN wind_speed < 10 THEN '5-10' ELSE '>=10' END AS wind,
                       avg(taxi_out_clean) AS m
                FROM rq1_model_data
                WHERE `set` != 'test' AND precipitation_1hr_missing = 0 AND wind_speed IS NOT NULL
                GROUP BY 1, 2''')
         .pivot(index="wind", columns="rain", values="m").reindex(["<5", "5-10", ">=10"]))
fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
axes[0].plot(by_cong["band"], by_cong["m"], marker="o", color=BLUE)
axes[0].set_xlabel("Departures in the same airport-hour (band of 10; 90 = 90 or more)")
axes[0].set_ylabel("Mean taxi-out (min)")
axes[0].set_title("Congestion")
by_wx.plot(kind="bar", ax=axes[1], color=[GREY, BLUE], rot=0, width=0.75, edgecolor="white", linewidth=1.5)
axes[1].set_xlabel("Wind speed (m/s)")
axes[1].set_ylabel("Mean taxi-out (min)")
axes[1].set_title("Rain and wind")
axes[1].legend(frameon=False)
fig.suptitle("Mean taxi-out time by congestion and weather (10 weather airports, 2023-2024)", y=1.02)
save_fig(fig, 3, "Mean taxi-out time by congestion and weather", "notebook 04, rq1_model_data")""")

code("""# Figure 4 and Table 1: RQ1 model comparison on the 2025 test set
mc = read("rq1_model_comparison").sort_values("mae_min")
labels = {"gradient_boosted_trees": "Gradient-boosted trees", "linear_regression": "Linear regression",
          "mlp_neural_network": "Neural network (MLP)", "historical_average": "Historical average"}
mc["Model"] = mc["model"].map(labels)
fig, ax = plt.subplots(figsize=(7, 2.8))
m_ = mc.iloc[::-1]
ax.errorbar(m_["mae_min"], range(len(m_)), xerr=[m_["mae_min"] - m_["mae_ci_low"], m_["mae_ci_high"] - m_["mae_min"]],
            fmt="o", markersize=7, color=BLUE, capsize=3)
for i, (v, r2) in enumerate(zip(m_["mae_min"], m_["r2"])):
    ax.text(v + 0.03, i, f"{v:.2f} min  (R2 {r2:.2f})", va="center", fontsize=9)
ax.set_yticks(range(len(m_)))
ax.set_yticklabels(m_["Model"])
ax.set_xlim(5.9, 6.7)
ax.grid(axis="x", color="#e5e5e5", linewidth=0.6)
ax.set_xlabel("Mean absolute error, taxi-out (min); bars = 95% bootstrap interval")
ax.set_title("Taxi-out prediction on 2025 flights (10 weather airports)")
save_fig(fig, 4, "RQ1 model comparison on the 2025 test set", "notebook 04, rq1_model_comparison")
save_table(mc[["Model", "mae_min", "mae_ci_low", "mae_ci_high", "rmse_min", "r2"]].round(3), 1,
           "RQ1 model comparison on the 2025 test set", "notebook 04, rq1_model_comparison")""")

code("""# Figure 5: SHAP importance; Figure 6 and Table 2: effect sizes
FEATURES = {"origin": "Airport", "airline": "Airline", "scheduled_dep_hour": "Scheduled departure hour",
            "airport_hour_departure_count": "Departures in the airport-hour", "aircraft_family": "Aircraft family",
            "air_temperature": "Air temperature", "precipitation_1hr": "Precipitation (1 h)", "month": "Month",
            "wind_speed": "Wind speed", "day_of_week": "Day of week", "precipitation_1hr_missing": "Precipitation missing",
            "origin_hour_arrival_count": "Arrivals in the airport-hour", "aircraft_group": "Aircraft size class"}
shap_imp = read("rq1_shap_importance").sort_values("mean_abs_shap_min")
shap_imp["feature"] = shap_imp["feature"].map(FEATURES).fillna(shap_imp["feature"])
fig, ax = plt.subplots(figsize=(6.5, 4))
ax.barh(shap_imp["feature"], shap_imp["mean_abs_shap_min"], color=BLUE)
ax.set_xlabel("Mean |SHAP value| (minutes of predicted taxi-out)")
ax.set_title("What drives predicted taxi-out time (gradient-boosted trees)")
save_fig(fig, 5, "SHAP feature importance for taxi-out", "notebook 04, rq1_shap_importance")

eff = read("rq1_effect_sizes")
names = {"deps_10": "+10 departures in the airport-hour", "arrs_10": "+10 arrivals in the airport-hour", "rain": "Rain in the hour",
         "wind_speed": "Wind, per m/s", "air_temperature": "Temperature, per deg C",
         "C(aircraft_group)[T.regional_jet]": "Regional jet vs narrow-body", "C(aircraft_group)[T.wide_body]": "Wide-body vs narrow-body"}
eff["Factor"] = eff["term"].map(names)
e = eff.iloc[::-1]
fig, ax = plt.subplots(figsize=(7, 3.4))
ax.errorbar(e["minutes"], range(len(e)), xerr=[e["minutes"] - e["ci_low"], e["ci_high"] - e["minutes"]], fmt="o", color=BLUE, capsize=3)
ax.axvline(0, color="black", linewidth=0.8)
ax.set_yticks(range(len(e)))
ax.set_yticklabels(e["Factor"])
ax.set_xlabel("Change in taxi-out time (min), 95% interval")
ax.set_title("Effect sizes (airport, hour, month and weekday held constant)")
save_fig(fig, 6, "RQ1 effect sizes on taxi-out time", "notebook 04, rq1_effect_sizes")
save_table(eff[["Factor", "minutes", "ci_low", "ci_high", "kg_co2_per_flight"]].round(3), 2,
           "RQ1 effect sizes in minutes and kg CO2 per flight", "notebook 04, rq1_effect_sizes")""")

code("""# Figure 7 and Table 3: EM06DS classification models under the time-based split (B5)
cm = read("model_comparison_test_2025").sort_values("pr_auc")
cm["model"] = cm["model"].map({"majority_class": "Majority class", "logistic_regression": "Logistic regression",
                               "gbt_classifier": "Gradient-boosted trees", "baseline_mlp": "Baseline MLP",
                               "deep_mlp": "Deep MLP", "wide_mlp": "Wide MLP"})
fig, ax = plt.subplots(figsize=(7, 3))
y = np.arange(len(cm))
ax.barh(y + 0.2, cm["roc_auc"], 0.38, color=BLUE, label="ROC-AUC (chance = 0.50)")
ax.barh(y - 0.2, cm["pr_auc"], 0.38, color=ORANGE, label="PR-AUC (chance = 0.27)")
ax.set_yticks(y)
ax.set_yticklabels(cm["model"])
ax.set_xlim(0, 0.8)
ax.legend(frameon=False, fontsize=8, loc="lower right")
ax.set_title("High avoidable-emission classification, 2025 test set")
save_fig(fig, 7, "EM06DS classification models vs baselines (time-based split)", "notebook 02, model_comparison_test_2025")
save_table(cm.round(4), 3, "Classification metrics on the 2025 test set", "notebook 02, model_comparison_test_2025")""")

code("""# Figures 8-11 and Table 4: RQ2 airport performance
r = read("rq2_airport_ranking").sort_values("adjusted_co2_kg_per_movement").reset_index(drop=True)
fig, ax = plt.subplots(figsize=(7, 11))
colors = [BLUE if v < 0 else RED for v in r["adjusted_co2_kg_per_movement"]]
for i, row in r.iterrows():
    ax.errorbar(row["adjusted_co2_kg_per_movement"], i,
                xerr=[[row["adjusted_co2_kg_per_movement"] - row["adjusted_ci_low"]], [row["adjusted_ci_high"] - row["adjusted_co2_kg_per_movement"]]],
                fmt="o", markersize=3, capsize=2, color=colors[i])
ax.axvline(0, color="black", linewidth=0.8)
ax.set_yticks(range(len(r)))
ax.set_yticklabels(r["airport"], fontsize=6)
ax.invert_yaxis()
ax.set_xlabel("Extra ground CO2 per movement vs network average (kg)")
ax.set_title("Airport ground operations performance, 76 major U.S. airports\\n(blue = better than average, red = worse; conventional 95% intervals)", fontsize=10)
save_fig(fig, 8, "RQ2 adjusted ground CO2 per movement by airport", "notebook 05, rq2_airport_ranking")

fig, ax = plt.subplots(figsize=(5.5, 5))
ax.scatter(r["rank_raw"], r["rank_adjusted"], s=14, color=BLUE)
for _, row in r.iterrows():
    if abs(row["rank_raw"] - row["rank_adjusted"]) >= 20 or row["airport"] in ("ATL", "JFK", "PDX"):
        ax.annotate(row["airport"], (row["rank_raw"], row["rank_adjusted"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
ax.plot([1, 76], [1, 76], linestyle="--", color=GREY)
ax.set_xlabel("Rank by raw CO2 per movement (1 = lowest)")
ax.set_ylabel("Rank under comparable conditions (1 = best)")
ax.set_title("Raw vs adjusted airport ranking")
save_fig(fig, 9, "Raw vs adjusted airport ranking", "notebook 05, rq2_airport_ranking")

yr = read("rq2_airport_effects_by_year")
fig, ax = plt.subplots(figsize=(5.5, 5))
ax.scatter(yr["adj_2023"], yr["adj_2025"], s=14, color=BLUE)
lim = [min(yr[["adj_2023", "adj_2025"]].min()) - 10, max(yr[["adj_2023", "adj_2025"]].max()) + 10]
ax.plot(lim, lim, linestyle="--", color=GREY)
ax.set_xlabel("Adjusted kg CO2 per movement, 2023")
ax.set_ylabel("Adjusted kg CO2 per movement, 2025")
rho = yr["adj_2023"].corr(yr["adj_2025"], method="spearman")
ax.set_title(f"Stability of airport effects, 2023 vs 2025 (Spearman {rho:.2f})")
save_fig(fig, 10, "Year-to-year stability of airport effects", "notebook 05, rq2_airport_effects_by_year")

prof = read("rq2_airport_profile")
fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
for ax, col, lab in [(axes[0], "avg_departures_in_hour", "Average departures in the airport-hour"),
                     (axes[1], "departures_per_runway_per_day", "Departures per runway per day")]:
    ax.scatter(prof[col], prof["adjusted_co2_kg_per_movement"], s=14, color=BLUE)
    rho = prof[col].corr(prof["adjusted_co2_kg_per_movement"], method="spearman")
    ax.set_xlabel(lab)
    ax.set_ylabel("Adjusted kg CO2 per movement")
    ax.set_title(f"Spearman {rho:.2f}")
    ax.axhline(0, color="black", linewidth=0.6)
fig.suptitle("Airport characteristics and ground operations performance", y=1.02)
save_fig(fig, 11, "Airport characteristics vs adjusted performance", "notebook 05, rq2_airport_profile")

cols = ["airport", "movements", "adjusted_co2_kg_per_movement", "adjusted_ci_low", "adjusted_ci_high",
        "taxi_out_effect_min", "taxi_in_effect_min", "co2_kg_per_movement", "rank_adjusted", "rank_raw", "rank_em06ds"]
save_table(pd.concat([r.head(10).assign(group="best 10"), r.tail(10).assign(group="worst 10")])[["group"] + cols].round(1), 4,
           "RQ2 best and worst 10 airports under comparable conditions", "notebook 05, rq2_airport_ranking")""")

code("""# Figures 12-14 and Table 5: RQ3 scenarios
ns = read("rq3_national_savings").set_index("scenario")[["low", "central", "high"]] / 1e6
fig, ax = plt.subplots(figsize=(7.5, 3.2))
yy = np.arange(len(ns))
ax.barh(yy, ns["central"], color=BLUE, xerr=[ns["central"] - ns["low"], ns["high"] - ns["central"]], capsize=3)
ax.set_yticks(yy)
ax.set_yticklabels(ns.index)
ax.invert_yaxis()
ax.set_xlabel("Mt CO2 saved per year (2025 traffic, 76 airports); bars = low to high assumptions")
ax.set_title("Emission reductions without extra delay or capacity loss")
save_fig(fig, 12, "RQ3 national savings by measure", "notebook 06, rq3_national_savings")
save_table((ns * 1e6).round(0).reset_index(), 5, "RQ3 tonnes CO2 saved per year (low, central, high)", "notebook 06, rq3_national_savings")

tor = read("rq3_sensitivity").sort_values("range")
tor["assumption"] = tor["assumption"].map({
    "grid_kg_per_kwh": "Grid CO2 intensity", "gpu_kw": "Ground power demand", "cooldown_min": "Engine cool-down after landing",
    "apu_min_with_gpu": "APU minutes still needed with ground power", "warmup_min": "Engine warm-up before take-off",
    "apu_fuel": "APU fuel flow", "set_eligible_other": "Single-engine taxi eligibility (no weather data)",
    "hold_share": "Gate hold: share of queue moved to the gate", "set_saving": "Single-engine taxi fuel saving",
    "apu_share_of_turn": "APU running share of turnaround"})
base_total = read("rq3_national_savings").set_index("scenario").loc["Combined 1 + 2 + 3", "central"] / 1e6
fig, ax = plt.subplots(figsize=(7.5, 3.8))
for i, row in enumerate(tor.itertuples()):
    ax.barh(i, row.high / 1e6 - base_total, left=base_total, color=BLUE, label="High value" if i == 0 else None)
    ax.barh(i, row.low / 1e6 - base_total, left=base_total, color=ORANGE, label="Low value" if i == 0 else None)
ax.axvline(base_total, color="black", linewidth=0.8)
ax.set_yticks(range(len(tor)))
ax.set_yticklabels(tor["assumption"])
ax.set_xlabel("Combined Mt CO2 saved per year, one assumption moved at a time")
ax.legend(frameon=False, fontsize=8, loc="lower right")
ax.set_title(f"Sensitivity of the combined saving (central {base_total:.2f} Mt)")
save_fig(fig, 13, "RQ3 sensitivity analysis", "notebook 06, rq3_sensitivity")

sav = read("rq3_airport_savings")
fig, ax = plt.subplots(figsize=(5.8, 4.4))
ax.scatter(sav["adjusted_co2_kg_per_movement"], sav["s1_kg_per_movement"], s=14, color=BLUE)
for _, row in sav.iterrows():
    if row["airport"] in ("JFK", "EWR", "ORD", "LGA", "ATL", "PDX"):
        ax.annotate(row["airport"], (row["adjusted_co2_kg_per_movement"], row["s1_kg_per_movement"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
rho = sav["adjusted_co2_kg_per_movement"].corr(sav["s1_kg_per_movement"], method="spearman")
ax.set_xlabel("RQ2 adjusted kg CO2 per movement")
ax.set_ylabel("Gate-hold saving, kg CO2 per movement (central)")
ax.set_title(f"Less efficient airports have more to gain (Spearman {rho:.2f})")
save_fig(fig, 14, "Gate-hold saving vs RQ2 airport performance", "notebook 06, rq3_airport_savings")""")

code("""# Figure 15 and Table 6: Spark scaling benchmark
b = read("scaling_benchmark")
b = b[b["run_at"] == b.groupby("workers")["run_at"].transform("max")]
m = b.groupby(["workload", "fraction", "workers"], as_index=False).agg(flights=("flights", "first"), seconds=("seconds", "median"))
full = m[m["fraction"] == 1.0]
fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
for wl, label, color in [("sql_congestion_aggregation", "SQL congestion aggregation", BLUE), ("mllib_fixed_effects_regression", "MLlib fixed-effects regression", ORANGE)]:
    g = full[full["workload"] == wl].sort_values("workers")
    axes[0].plot(g["workers"], g["seconds"], marker="o", color=color, label=label)
    axes[1].plot(g["workers"], g["seconds"].iloc[0] / g["seconds"], marker="o", color=color, label=label)
axes[1].plot([1, 4], [1, 4], linestyle="--", color=GREY, label="Ideal linear speed-up")
for ax in axes:
    ax.set_xticks([1, 2, 4])
    ax.set_xlabel("Workers (4 cores each)")
    ax.legend(frameon=False, fontsize=8)
axes[0].set_ylabel(f"Seconds (median of 2 runs), {full['flights'].max() / 1e6:.1f}M flights")
axes[1].set_ylabel("Speed-up vs 1 worker")
fig.suptitle("Spark scaling on Databricks (m5d.xlarge workers)", y=1.02)
save_fig(fig, 15, "Spark scaling: runtime and speed-up by cluster size", "notebook 07, scaling_benchmark")
save_table(m.pivot_table(index=["workload", "fraction"], columns="workers", values="seconds").reset_index(), 6,
           "Spark scaling benchmark, median seconds", "notebook 07, scaling_benchmark")""")

code("""# Table 7: variance inflation factors (VIF) for the RQ1 regression (notebook 04, cell "Effect sizes")
# Sample: about 500,000 training flights chosen by a hash of the row (the same rows on every run and platform).
# Same variables as the OLS model: VIF is computed (a) for the predictors alone and (b) inside the full design with
# aircraft group, airport, hour, month and weekday dummies, which is the model actually estimated.
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tools.tools import add_constant

v = sql('''SELECT airport_hour_departure_count, origin_hour_arrival_count, precipitation_1hr, precipitation_1hr_missing,
                  wind_speed, air_temperature, aircraft_group, origin, scheduled_dep_hour, month, day_of_week
           FROM rq1_model_data
           WHERE `set` = 'train'
             AND pmod(hash(flight_date, origin, airline, aircraft_family, scheduled_dep_hour, airport_hour_departure_count,
                           origin_hour_arrival_count, air_temperature, wind_speed, taxi_out_clean), 1000) < 137''').dropna()
X = pd.DataFrame({
    "Departures in the airport-hour (per 10)": v["airport_hour_departure_count"] / 10,
    "Arrivals in the airport-hour (per 10)": v["origin_hour_arrival_count"] / 10,
    "Rain in the hour (0/1)": ((v["precipitation_1hr"] > 0) & (v["precipitation_1hr_missing"] == 0)).astype(float),
    "Wind speed (m/s)": v["wind_speed"].astype(float),
    "Air temperature (deg C)": v["air_temperature"].astype(float),
})
groups = pd.get_dummies(v["aircraft_group"], prefix="Aircraft group", drop_first=True, dtype=float)
X = pd.concat([X, groups], axis=1)
fe = pd.get_dummies(v[["origin", "scheduled_dep_hour", "month", "day_of_week"]].astype(str), drop_first=True, dtype=float)

def vifs(design, names):
    d = add_constant(design).values
    cols = list(add_constant(design).columns)
    return [round(variance_inflation_factor(d, cols.index(n)), 2) for n in names]

vif = pd.DataFrame({"variable": X.columns,
                    "VIF_predictors_only": vifs(X, X.columns),
                    "VIF_with_fixed_effects": vifs(pd.concat([X, fe], axis=1), X.columns)})
print(f"Flights: {len(v):,} (training period, 10 weather airports)")
print(vif.to_string(index=False))
print("Rule of thumb: VIF above 5 (strict) or 10 (lenient) signals problematic multicollinearity.")
save_table(vif, 7, "Variance inflation factors, RQ1 regression variables", "notebook 08, rq1_model_data")""")

code("""# Index of figures and tables
idx = pd.DataFrame(index)
idx.to_csv(f"{OUT_DIR}/INDEX.csv", index=False)
print(idx.to_string(index=False))""")

DATABRICKS_HEADER = """# Figures and tables for the thesis

Reads the result tables written by notebooks 01-07 (nothing is re-estimated) and saves numbered figures (PNG, 300 dpi)
and tables (CSV) to `/Volumes/new/airgreenops/project_data/airgreenops/figures/`, copied to `docs/figures/` in the repository.
Also runs a variance inflation factor (VIF) check on the RQ1 regression variables.
The same cells run in Google Colab: `colab/figures_tables_colab.ipynb`."""

DATABRICKS_CONNECT = """# Configuration (Databricks: tables are read with Spark SQL)
spark.sql("USE CATALOG `new`")
spark.sql("USE SCHEMA `airgreenops`")

def sql(query):
    return spark.sql(query).toPandas()

def read(table):
    return spark.table(table).toPandas()

OUT_DIR = "/Volumes/new/airgreenops/project_data/airgreenops/figures\""""

common = cells
cells = []
md(DATABRICKS_HEADER)
code(DATABRICKS_CONNECT)
DATABRICKS_SETUP = cells

COLAB_SETUP = [
    colab.md("""# Figures and tables for the thesis (Google Colab)

The data stays in Databricks: this notebook sends SQL queries to the Databricks SQL warehouse and draws the figures in Colab.
The cells are the same as notebook 08 on Databricks; only the connection differs. Output: `figures/` and `airgreenops_figures.zip`.

""" + colab.TOKEN_NOTE),
    colab.code('%pip install -q "databricks-sql-connector[pyarrow]==4.6.0"'),
    colab.code(colab.CONNECT),
    colab.code('OUT_DIR = "figures"'),
]
COLAB_END = [colab.code("""# Download all figures and tables as one zip file
import shutil

shutil.make_archive("airgreenops_figures", "zip", OUT_DIR)
try:
    from google.colab import files
    files.download("airgreenops_figures.zip")
except ImportError:
    print("Saved airgreenops_figures.zip")""")]

nb = {
    "cells": DATABRICKS_SETUP + common,
    "metadata": {"application/vnd.databricks.v1+notebook": {"language": "python", "notebookName": "08_figures_tables"},
                 "language_info": {"name": "python"}},
    "nbformat": 4,
    "nbformat_minor": 0,
}
for path, content in [(OUT, nb), (OUT_COLAB, colab.notebook(COLAB_SETUP + [dict(c, execution_count=None) for c in common] + COLAB_END))]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(content, indent=1, ensure_ascii=False) + "\n")
    print("written", path, len(content["cells"]), "cells")
