"""RQ3 scenario calculator shared by the dashboard (notebook 03).

Same formulas and assumptions as notebook 06. Inputs are the component tables notebook 06 saves:
rq3_components_departures, rq3_components_arrivals, rq3_components_turnarounds.
"""
import pandas as pd

CO2 = 3.16
GROUPS = ["regional_jet", "narrow_body", "wide_body"]

# (low, central, high); "low" gives the smaller saving
A = {
    "hold_share": (0.25, 0.50, 0.75),
    "set_saving": (0.30, 0.40, 0.50),
    "warmup_min": (5, 3, 2),
    "cooldown_min": (5, 3, 2),
    "set_eligible_other": (0.70, 0.85, 0.95),
    "apu_share_of_turn": (0.30, 0.50, 0.80),
    "apu_min_with_gpu": (15, 10, 5),
    "grid_kg_per_kwh": (0.45, 0.37, 0.25),
}
APU_FUEL_KG_MIN = {"regional_jet": (0.8, 1.0, 1.3), "narrow_body": (1.5, 1.9, 2.3), "wide_body": (3.5, 4.5, 5.5)}
GPU_KW = {"regional_jet": (39, 30, 21), "narrow_body": (65, 50, 35), "wide_body": (156, 120, 84)}
LEVEL = {"low": 0, "central": 1, "high": 2}


def pick(level="central"):
    i = LEVEL[level]
    p = {k: v[i] for k, v in A.items()}
    p["apu_fuel"] = {g: APU_FUEL_KG_MIN[g][i] for g in GROUPS}
    p["gpu_kw"] = {g: GPU_KW[g][i] for g in GROUPS}
    return p


def scenario(dep_agg, arr_agg, turn_agg, p):
    """Per-airport savings (kg CO2) for one set of assumptions."""
    d, a, t = dep_agg.copy(), arr_agg.copy(), turn_agg.copy()
    kw = d["aircraft_group"].map(p["gpu_kw"])

    d["s1_kg"] = p["hold_share"] * d["excess_fuel_kg"] * CO2 - p["hold_share"] * d["excess_min"] / 60 * kw * p["grid_kg_per_kwh"]
    d["s1_offpeak_kg"] = (p["hold_share"] * d["excess_fuel_kg_offpeak"] * CO2
                          - p["hold_share"] * d["excess_min_offpeak"] / 60 * kw * p["grid_kg_per_kwh"])

    wu, cd = p["warmup_min"], p["cooldown_min"]
    out_elig = d[f"set_out_fuel_eligible_w{wu}"] + p["set_eligible_other"] * d[f"set_out_fuel_unknown_w{wu}"]
    d["s2_out_kg"] = p["set_saving"] * out_elig * CO2
    a["s2_in_kg"] = p["set_saving"] * p["set_eligible_other"] * a[f"set_in_fuel_c{cd}"] * CO2

    h = int(round(p["hold_share"] * 100))
    out_after = d[f"set_out_fuel_eligible_w{wu}_h{h}"] + p["set_eligible_other"] * d[f"set_out_fuel_unknown_w{wu}_h{h}"]
    d["s2_out_after_hold_kg"] = p["set_saving"] * out_after * CO2

    s, m = int(round(p["apu_share_of_turn"] * 100)), p["apu_min_with_gpu"]
    t_apu = t["aircraft_group"].map(p["apu_fuel"])
    t_kw = t["aircraft_group"].map(p["gpu_kw"])
    t["s3_kg"] = t[f"apu_avoid_min_s{s}_m{m}"] * (t_apu * CO2 - t_kw / 60 * p["grid_kg_per_kwh"])
    t["apu_baseline_kg"] = t["turn_min_total"] * p["apu_share_of_turn"] * t_apu * CO2

    out = (
        d.groupby("airport").agg({"departures": "sum", "out_fuel_kg": "sum", "s1_kg": "sum", "s1_offpeak_kg": "sum",
                                  "s2_out_kg": "sum", "s2_out_after_hold_kg": "sum"})
        .join(a.groupby("airport")[["arrivals", "in_fuel_kg", "s2_in_kg"]].sum(), how="outer")
        .join(t.groupby("airport")[["turns", "s3_kg", "apu_baseline_kg"]].sum(), how="outer")
        .fillna(0)
    )
    out["baseline_ground_co2_kg"] = (out["out_fuel_kg"] + out["in_fuel_kg"]) * CO2 + out["apu_baseline_kg"]
    out["s2_kg"] = out["s2_out_kg"] + out["s2_in_kg"]
    out["combined_kg"] = out["s1_kg"] + out["s2_out_after_hold_kg"] + out["s2_in_kg"] + out["s3_kg"]
    return out
