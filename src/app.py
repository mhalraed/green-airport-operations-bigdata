"""Databricks App: the RQ2 and RQ3 dashboard tabs (thesis_dashboard.py), reading the results through the SQL warehouse.

This folder (src/) is the app's source code: app.py, app.yaml, requirements.txt and the shared modules.
The app signs in to Databricks as its own service principal, which has read access to the result tables only.
"""
import os

import gradio as gr
from databricks import sql
from databricks.sdk.core import Config

import thesis_dashboard as thesis

cfg = Config()
HTTP_PATH = f"/sql/1.0/warehouses/{os.environ['DATABRICKS_WAREHOUSE_ID']}"


def read(table):
    with sql.connect(server_hostname=cfg.host, http_path=HTTP_PATH, credentials_provider=lambda: cfg.authenticate) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM new.airgreenops.{table}")
            return cursor.fetchall_arrow().to_pandas()


data = thesis.load(read)

with gr.Blocks(title="AirGreenOps Dashboard") as demo:
    gr.Markdown("# AirGreenOps: airport ground emissions\n"
                "Results for 76 major U.S. airports (BTS on-time data 2023-2025, ICAO engine databank fuel flow).")
    thesis.add_tabs(gr, demo, data)

if __name__ == "__main__":
    demo.launch()
