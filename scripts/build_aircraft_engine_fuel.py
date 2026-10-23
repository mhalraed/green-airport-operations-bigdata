"""Build reference/aircraft_engine_fuel.csv: taxi fuel burn per aircraft family.

Method
- Each rule maps BTS Schedule B-43 MODEL strings (regular expression) to an aircraft family,
  its engine family, the number of engines and a size class.
- Idle fuel flow comes from the ICAO Aircraft Engine Emissions Databank (EASA, v32, 03/2026),
  column "Fuel Flow Idle (kg/sec)". Idle is the 7% thrust setting ICAO uses for taxi.
- Per engine family, the median idle fuel flow over all databank rows whose
  "Engine Identification" matches the engine pattern is used.
- Taxi fuel burn (kg/min) = median idle fuel flow (kg/s per engine) x engines x 60.

Usage: python scripts/build_aircraft_engine_fuel.py <path to edb xlsx>
"""
import re
import sys
import pandas as pd

# (rule_id, B-43 MODEL regex, aircraft family, engine family label, ICAO databank pattern, engines, size class)
RULES = [
    ("E175", r"^(?:ERJ-?170-200|E175)", "Embraer E175", "CF34-8E", r"^CF34-8E", 2, "regional_jet"),
    ("E170", r"^(?:ERJ-?170-100|E170)", "Embraer E170", "CF34-8E", r"^CF34-8E", 2, "regional_jet"),
    ("E190", r"^(?:ERJ-?190|E190)", "Embraer E190", "CF34-10E", r"^CF34-10E", 2, "regional_jet"),
    ("ERJ145", r"^(ERJ|EMB)-?1[34]5", "Embraer ERJ145 family", "AE3007A", r"^AE3007A", 2, "regional_jet"),
    ("CRJ200", r"^(?:CL-600-2B19|CRJ-?200)", "Bombardier CRJ200", "CF34-3B", r"^CF34-3B", 2, "regional_jet"),
    ("CRJ700", r"^CL-600-2C1[01]", "Bombardier CRJ700", "CF34-8C", r"^CF34-8C", 2, "regional_jet"),
    ("CRJ900", r"^CL-600-2D(24|15)", "Bombardier CRJ900", "CF34-8C", r"^CF34-8C", 2, "regional_jet"),
    ("CRJ1000", r"^CL-600-2E25", "Bombardier CRJ1000", "CF34-8C", r"^CF34-8C", 2, "regional_jet"),
    ("A220-100", r"^(BD-500-1A10|A220-100)", "Airbus A220-100", "PW1500G", r"^PW15", 2, "narrow_body"),
    ("A220-300", r"^(BD-500-1A11|A220-300)", "Airbus A220-300", "PW1500G", r"^PW15", 2, "narrow_body"),
    ("737MAX8", r"^(?:737-8|MAX ?8|737 ?MAX ?8|737-8 ?MAX|737-8200)$|^737-?MAX ?8", "Boeing 737 MAX 8", "LEAP-1B", r"^LEAP-1B", 2, "narrow_body"),
    ("737MAX9", r"^(?:737-9|MAX ?9|737 ?MAX ?9|737-9 ?MAX)$|^737-?MAX ?9", "Boeing 737 MAX 9", "LEAP-1B", r"^LEAP-1B", 2, "narrow_body"),
    ("737MAX7", r"^(737-7|MAX ?7|737 ?MAX ?7)$", "Boeing 737 MAX 7", "LEAP-1B", r"^LEAP-1B", 2, "narrow_body"),
    ("737-700", r"^737-7[0-9A-Z]{2}", "Boeing 737-700", "CFM56-7B", r"^CFM56-7B", 2, "narrow_body"),
    ("737-800", r"^737-8[0-9A-Z]{2}", "Boeing 737-800", "CFM56-7B", r"^CFM56-7B", 2, "narrow_body"),
    ("737-900", r"^737-9[0-9A-Z]{2}", "Boeing 737-900/900ER", "CFM56-7B", r"^CFM56-7B", 2, "narrow_body"),
    ("737-classic", r"^737-[345][0-9A-Z]{2}", "Boeing 737-300/400/500", "CFM56-3", r"^CFM56-3", 2, "narrow_body"),
    ("717", r"^717", "Boeing 717-200", "BR715", r"^BR700-715", 2, "narrow_body"),
    ("757-200", r"^757-2", "Boeing 757-200", "RB211-535 / PW2000", r"^(RB211-535|PW20[34])", 2, "narrow_body"),
    ("757-300", r"^757-3", "Boeing 757-300", "RB211-535 / PW2000", r"^(RB211-535|PW20[34])", 2, "narrow_body"),
    ("767-300", r"^767-3", "Boeing 767-300", "CF6-80C2 / PW4000", r"^(CF6-80C2|PW40[56])", 2, "wide_body"),
    ("767-400", r"^767-4", "Boeing 767-400", "CF6-80C2", r"^CF6-80C2", 2, "wide_body"),
    ("777-200", r"^777-2", "Boeing 777-200", "GE90 / PW4000-112 / Trent 800", r"^(GE90-9|PW40[789]|Trent 8)", 2, "wide_body"),
    ("777-300", r"^777-3", "Boeing 777-300ER", "GE90-115B", r"^GE90-11", 2, "wide_body"),
    ("787", r"^787", "Boeing 787", "GEnx-1B / Trent 1000", r"^(GEnx-1B|Trent 10)", 2, "wide_body"),
    ("A319-CFM", r"^A319-1[01][0-9]", "Airbus A319 (CFM56-5)", "CFM56-5", r"^CFM56-5[AB]", 2, "narrow_body"),
    ("A319-IAE", r"^A319-13[0-9]", "Airbus A319 (V2500)", "V2500", r"^V25", 2, "narrow_body"),
    ("A320neo-LEAP", r"^A320-25[0-9]N", "Airbus A320neo (LEAP-1A)", "LEAP-1A", r"^LEAP-1A", 2, "narrow_body"),
    ("A320neo-PW", r"^A320-27[0-9]N", "Airbus A320neo (PW1100G)", "PW1100G", r"^PW11", 2, "narrow_body"),
    ("A320-CFM", r"^A320-21[0-9]", "Airbus A320 (CFM56-5)", "CFM56-5", r"^CFM56-5[AB]", 2, "narrow_body"),
    ("A320-IAE", r"^A320-23[0-9]", "Airbus A320 (V2500)", "V2500", r"^V25", 2, "narrow_body"),
    ("A321neo-LEAP", r"^A321-25[0-9]N", "Airbus A321neo (LEAP-1A)", "LEAP-1A", r"^LEAP-1A", 2, "narrow_body"),
    ("A321neo-PW", r"^A321-27[0-9]N", "Airbus A321neo (PW1100G)", "PW1100G", r"^PW11", 2, "narrow_body"),
    ("A321-CFM", r"^A321-21[0-9]", "Airbus A321 (CFM56-5B)", "CFM56-5B", r"^CFM56-5B", 2, "narrow_body"),
    ("A321-IAE", r"^A321-23[0-9]", "Airbus A321 (V2500)", "V2500", r"^V25", 2, "narrow_body"),
    ("A330", r"^A330-[23]", "Airbus A330-200/300", "CF6-80E / PW4100 / Trent 700", r"^(CF6-80E|PW41|Trent 7[0-9]{2}\b)", 2, "wide_body"),
    ("A330neo", r"^A330-9", "Airbus A330-900neo", "Trent 7000", r"^Trent ?7000", 2, "wide_body"),
    ("A350", r"^A350", "Airbus A350-900", "Trent XWB-84", r"^Trent XWB-84", 2, "wide_body"),
]


def main(edb_path):
    edb = pd.read_excel(edb_path, sheet_name="Gaseous Emissions and Smoke")
    edb["engine_id"] = edb["Engine Identification"].astype(str).str.strip()
    edb["idle_ff"] = pd.to_numeric(edb["Fuel Flow Idle (kg/sec)"], errors="coerce")
    rows = []
    for rid, model_re, fam, eng, edb_re, n, size in RULES:
        m = edb[edb.engine_id.apply(lambda e: re.search(edb_re, e) is not None) & edb.idle_ff.notna()]
        if m.empty:
            raise SystemExit(f"No databank rows for {rid} ({edb_re})")
        ff = float(m.idle_ff.median())
        rows.append({
            "rule_id": rid,
            "model_regex": model_re,
            "aircraft_family": fam,
            "engine_family": eng,
            "edb_engine_regex": edb_re,
            "engines": n,
            "size_class": size,
            "edb_rows": len(m),
            "idle_fuel_flow_kg_s_per_engine": round(ff, 4),
            "taxi_fuel_kg_per_min": round(ff * n * 60, 2),
            "source": "ICAO Aircraft Engine Emissions Databank v32 (EASA, 03/2026), median Fuel Flow Idle",
        })
    out = pd.DataFrame(rows)
    out.to_csv("reference/aircraft_engine_fuel.csv", index=False)
    print(out[["rule_id", "engine_family", "edb_rows", "idle_fuel_flow_kg_s_per_engine", "taxi_fuel_kg_per_min"]].to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
