"""Airport performance (RQ2) and reduction scenario (RQ3) dashboard tabs.

Shared by the Databricks dashboard (notebook 03) and the Colab dashboard (colab/dashboard_colab.ipynb), so both show
the same results. Each notebook supplies `read(table_name)`, which returns a table of `new.airgreenops` as pandas.
"""
import matplotlib.pyplot as plt
import pandas as pd

import rq3_scenarios as rq3

RQ2_DEFAULT = ["ATL", "JFK", "ORD", "DEN", "LAX"]


def load(read):
    """Reads the results of notebooks 05 and 06; stops if the scenario calculator does not reproduce notebook 06."""
    data = {
        "rq2": read("rq2_airport_ranking").sort_values("adjusted_co2_kg_per_movement").reset_index(drop=True),
        "dep": read("rq3_components_departures"),
        "arr": read("rq3_components_arrivals"),
        "turn": read("rq3_components_turnarounds"),
    }
    national = read("rq3_national_savings")
    dash_total = rq3.scenario(data["dep"], data["arr"], data["turn"], rq3.pick("central"))["combined_kg"].sum() / 1000
    nb06_total = float(national.loc[national["scenario"] == "Combined 1 + 2 + 3", "central"].iloc[0])
    print(f"Combined saving, central: dashboard {dash_total:,.0f} t | notebook 06 {nb06_total:,.0f} t")
    if abs(dash_total - nb06_total) > 1:
        raise Exception("Dashboard scenario calculator does not match notebook 06")
    return data


def rq2_chart(data, selected):
    selected = selected or []
    r = data["rq2"]
    colors = ["#d62728" if a in selected else "#9aa5b1" for a in r["airport"]]
    fig, ax = plt.subplots(figsize=(7, 11))
    for i, row in r.iterrows():
        ax.errorbar(row["adjusted_co2_kg_per_movement"], i,
                    xerr=[[row["adjusted_co2_kg_per_movement"] - row["adjusted_ci_low"]], [row["adjusted_ci_high"] - row["adjusted_co2_kg_per_movement"]]],
                    fmt="o", markersize=3, capsize=2, color=colors[i])
    ax.axvline(0, linestyle="--", color="black", linewidth=0.8)
    ax.set_yticks(range(len(r)))
    ax.set_yticklabels(r["airport"], fontsize=6)
    ax.invert_yaxis()
    ax.set_xlabel("Extra ground CO2 per movement vs network average (kg), comparable conditions")
    ax.set_title("Airport ground operations performance (taxi-out + taxi-in)")
    plt.tight_layout()
    return fig


def rq2_table(data, selected):
    rq2 = data["rq2"]
    r = rq2[rq2["airport"].isin(selected)] if selected else pd.concat([rq2.head(5), rq2.tail(5)])
    return pd.DataFrame({
        "Airport": r["airport"],
        "Movements 2023-25": r["movements"].astype(int),
        "Adjusted kg CO2 / movement": r["adjusted_co2_kg_per_movement"].round(1),
        "Raw kg CO2 / movement": r["co2_kg_per_movement"].round(1),
        "Rank adjusted (1 = best)": r["rank_adjusted"].astype(int),
        "Rank raw": r["rank_raw"].astype(int),
        "Rank EM06DS green score": r["rank_em06ds"],
    })


def rq3_calculate(data, airport, hold_share, set_saving, warmup, cooldown, eligible_other, apu_share, apu_min, grid, level):
    p = rq3.pick(level)
    p.update({"hold_share": float(hold_share), "set_saving": float(set_saving), "warmup_min": int(warmup),
              "cooldown_min": int(cooldown), "set_eligible_other": float(eligible_other), "apu_share_of_turn": float(apu_share),
              "apu_min_with_gpu": int(apu_min), "grid_kg_per_kwh": float(grid)})
    res = rq3.scenario(data["dep"], data["arr"], data["turn"], p)
    if airport != "All 76 airports":
        res = res.loc[[airport]]
    tot = res.sum(numeric_only=True)
    base = tot["baseline_ground_co2_kg"]
    measures = [("Gate hold", "s1_kg"), ("Gate hold, only when gates are free", "s1_offpeak_kg"),
                ("Single-engine taxi", "s2_kg"), ("Ground power at stand", "s3_kg"), ("Combined", "combined_kg")]
    table = pd.DataFrame({
        "Measure": [m for m, _ in measures],
        "Tonnes CO2 saved per year": [round(tot[c] / 1000, 0) for _, c in measures],
        "% of ground CO2 (taxi + APU)": [round(tot[c] / base * 100, 1) for _, c in measures],
    })
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.barh(table["Measure"], table["Tonnes CO2 saved per year"], color="#2ca02c")
    ax.invert_yaxis()
    ax.set_xlabel("Tonnes CO2 saved per year (2025 traffic)")
    ax.set_title(f"{airport}: baseline ground CO2 {base / 1e9:.2f} Mt" if airport == "All 76 airports" else f"{airport}: baseline ground CO2 {base / 1e6:.1f} kt")
    plt.tight_layout()
    return table, fig


def add_tabs(gr, demo, data):
    """Adds the two tabs; call inside `with gr.Blocks() as demo:`."""
    airports = data["rq2"]["airport"].tolist()

    with gr.Tab("Airport Performance: Comparable Conditions"):
        gr.Markdown("Extra ground CO2 per aircraft movement compared with the network average, holding airline, aircraft type, "
                    "time of day, season and traffic constant (RQ2, notebook 05). Negative = better than average. "
                    "Intervals use conventional standard errors and are likely too narrow; the ranking is stable across 2023-2025.")
        rq2_pick = gr.Dropdown(choices=airports, value=RQ2_DEFAULT, multiselect=True, label="Highlight airports")
        rq2_plot = gr.Plot(value=rq2_chart(data, RQ2_DEFAULT))
        rq2_df = gr.Dataframe(value=rq2_table(data, RQ2_DEFAULT), interactive=False)
        rq2_pick.change(lambda s: (rq2_chart(data, s), rq2_table(data, s)), inputs=rq2_pick, outputs=[rq2_plot, rq2_df])

    with gr.Tab("Reduction Scenarios: No Extra Delay"):
        gr.Markdown("Estimated CO2 saved per year (2025 traffic) by measures that keep take-off times, runway capacity and "
                    "turnaround times unchanged (RQ3, notebook 06). Fuel flow per taxi minute comes from the ICAO engine databank; "
                    "the inputs below are assumptions. Results are technical potential, not forecasts.")
        with gr.Row():
            sc_airport = gr.Dropdown(choices=["All 76 airports"] + airports, value="All 76 airports", label="Airport")
            sc_hold = gr.Radio([0.25, 0.5, 0.75], value=0.5, label="Gate hold: share of queue time moved to the gate")
            sc_set = gr.Slider(0.30, 0.50, value=0.40, step=0.05, label="Single-engine taxi: fuel saved per eligible minute")
        with gr.Row():
            sc_warm = gr.Radio([2, 3, 5], value=3, label="Engine warm-up before take-off (min)")
            sc_cool = gr.Radio([2, 3, 5], value=3, label="Engine cool-down after landing (min)")
            sc_elig = gr.Slider(0.70, 0.95, value=0.85, step=0.05, label="Share of flights eligible where no weather data")
        with gr.Row():
            sc_apu = gr.Radio([0.3, 0.5, 0.8], value=0.5, label="APU running share of turnaround today")
            sc_apu_min = gr.Radio([5, 10, 15], value=10, label="APU minutes still needed with ground power")
            sc_grid = gr.Slider(0.25, 0.45, value=0.37, step=0.01, label="Grid CO2 (kg per kWh)")
            sc_level = gr.Radio(["low", "central", "high"], value="central", label="APU fuel flow and ground power demand")
        sc_btn = gr.Button("Calculate savings")
        sc_table = gr.Dataframe(interactive=False)
        sc_plot = gr.Plot()
        sc_inputs = [sc_airport, sc_hold, sc_set, sc_warm, sc_cool, sc_elig, sc_apu, sc_apu_min, sc_grid, sc_level]
        calculate = lambda *values: rq3_calculate(data, *values)
        sc_btn.click(calculate, inputs=sc_inputs, outputs=[sc_table, sc_plot])
        demo.load(calculate, inputs=sc_inputs, outputs=[sc_table, sc_plot])
