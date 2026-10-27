"""Cells shared by the Google Colab notebooks in colab/ (written by scripts/build_notebook_08.py and build_colab_dashboard.py)."""

COLAB_METADATA = {"colab": {"provenance": []}, "kernelspec": {"display_name": "Python 3", "name": "python3"},
                  "language_info": {"name": "python"}}

TOKEN_NOTE = """**Before running:** in Databricks, create an access token (profile icon > Settings > Developer > Access tokens).
In Colab, open Secrets (key icon on the left), add it with the name `DATABRICKS_TOKEN` and allow notebook access.
Never paste the token into a cell: this notebook is public on GitHub."""

CONNECT = """# Connection to Databricks: the data stays in Databricks; each query runs on the SQL warehouse and returns a pandas table.
# The access token is read from Colab Secrets (name DATABRICKS_TOKEN).
import os
from databricks import sql as databricks_sql

try:
    from google.colab import userdata
    TOKEN = userdata.get("DATABRICKS_TOKEN")
except ImportError:  # outside Colab: environment variable
    TOKEN = os.environ["DATABRICKS_TOKEN"]

connection = databricks_sql.connect(server_hostname="dbc-621d6bfc-6584.cloud.databricks.com",
                                    http_path="/sql/1.0/warehouses/e1e7ec55e00b3788",
                                    access_token=TOKEN, catalog="new", schema="airgreenops")


def sql(query):
    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall_arrow().to_pandas()


def read(table):
    return sql(f"SELECT * FROM {table}")


print("Connected to Databricks:", len(sql("SHOW TABLES")), "tables in new.airgreenops")"""


def notebook(cells):
    return {"cells": cells, "metadata": COLAB_METADATA, "nbformat": 4, "nbformat_minor": 0}


def md(t):
    return {"cell_type": "markdown", "metadata": {}, "source": t}


def code(t):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": t}
