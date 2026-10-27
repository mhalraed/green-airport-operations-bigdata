"""Builds colab/dashboard_colab.ipynb: the RQ2 and RQ3 dashboard tabs in Google Colab, reading the results from Databricks.

The tabs come from src/thesis_dashboard.py, the same code as the Databricks dashboard (notebook 03).
"""
import json
import os

import colab_common as colab

OUT = "colab/dashboard_colab.ipynb"

cells = [
    colab.md("""# AirGreenOps dashboard (Google Colab)

Airport performance under comparable conditions (RQ2) and emission reduction scenarios without extra delay (RQ3).
The data stays in Databricks: this notebook reads the result tables of notebooks 05 and 06 through the Databricks SQL
warehouse, so the Spark cluster does not need to run. The tabs use the same code as the Databricks dashboard
(`src/thesis_dashboard.py`). The EM06DS prediction tabs score flights with Spark ML models, so they stay in notebook 03.

""" + colab.TOKEN_NOTE + """

Then Runtime > Run all. The last cell shows the dashboard and prints a public link (valid while this notebook runs)."""),
    colab.code('%pip install -q gradio==4.44.1 huggingface_hub==0.25.2 "databricks-sql-connector[pyarrow]==4.6.0"'),
    colab.code("""# Project code from GitHub: scenario calculator and dashboard tabs (src/)
import os
import subprocess
import sys

REPO_DIR = os.environ.get("AIRGREENOPS_REPO", "/content/green-airport-operations-bigdata")
if not os.path.exists(REPO_DIR):
    subprocess.run(["git", "clone", "--depth", "1", "https://github.com/mhalraed/green-airport-operations-bigdata.git", REPO_DIR],
                   check=True)
sys.path.insert(0, f"{REPO_DIR}/src")"""),
    colab.code(colab.CONNECT),
    colab.code("""# Results of notebooks 05 and 06; stops if the scenario calculator does not reproduce notebook 06
import thesis_dashboard as thesis

THESIS_DATA = thesis.load(read)"""),
    colab.code("""# Dashboard
import gradio as gr

with gr.Blocks(title="AirGreenOps Dashboard") as demo:
    gr.Markdown("# AirGreenOps: airport ground emissions\\n"
                "Results for 76 major U.S. airports (BTS on-time data 2023-2025, ICAO engine databank fuel flow).")
    thesis.add_tabs(gr, demo, THESIS_DATA)

demo.launch(share=True, debug=False)"""),
]

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(json.dumps(colab.notebook(cells), indent=1, ensure_ascii=False) + "\n")
print("written", OUT, len(cells), "cells")
