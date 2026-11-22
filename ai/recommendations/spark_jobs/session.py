"""Spark session, lake paths, and Parquet helpers for spark_jobs."""

import os
import re
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

LAKE_DIR = Path(os.environ.get("LAKE_DIR", "/data/lake"))
ONET_DIR = Path(os.environ.get("ONET_DIR", "/data/onet/raw_onet_data/db_31_0_csv"))
SYLLABI_CSV = Path(os.environ.get("SYLLABI_DIR", "/data/syllabi")) / "valid_triples_for_postgres.csv"


def get_spark(app_name="ClassWizard_Sprint4"):
    spark = (
        SparkSession.builder
        .appName(app_name)
        .master("local[*]")
        .config("spark.driver.memory", os.environ.get("SPARK_DRIVER_MEMORY", "2g"))
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def write_table(df, layer, name):
    """Write a table to the lake as Parquet and return it read back from disk."""
    path = str(LAKE_DIR / layer / name)
    df.write.mode("overwrite").parquet(path)
    return df.sparkSession.read.parquet(path)


def read_table(spark, layer, name):
    return spark.read.parquet(str(LAKE_DIR / layer / name))


def snake_case(name):
    """'O*NET-SOC Code' -> 'o_net_soc_code'. Parquet rejects spaces and symbols in column names."""
    return re.sub(r"[^0-9a-z]+", "_", name.strip().lower()).strip("_")


def term_key(column):
    """Lower-cased, single-spaced, trimmed text used to match terms."""
    return F.trim(F.regexp_replace(F.lower(column), r"\s+", " "))


def section(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)
