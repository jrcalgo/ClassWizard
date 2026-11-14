"""Bronze layer: load the catalog, syllabus triples, and O*NET files into Parquet as-is."""

import os

import psycopg
from pyspark.sql import functions as F

from spark_jobs.session import ONET_DIR, SYLLABI_CSV, section, snake_case, write_table

ONET_FILES = {
    "onet_occupations": "occupation_data.csv",
    "onet_job_zones": "job_zones.csv",
    "onet_essential_skills": "essential_skills.csv",
    "onet_transferable_skills": "transferable_skills.csv",
    "onet_knowledge": "knowledge.csv",
    "onet_software_skills": "software_skills.csv",
}

COURSES_SQL = "SELECT catalog_name, code, title, description, credit_min FROM courses"
COURSES_SCHEMA = "catalog_name string, code string, title string, description string, credit_min int"

LINKS_SQL = "SELECT course_code, target_code, kind FROM course_links"
LINKS_SCHEMA = "course_code string, target_code string, kind string"


def read_csv(spark, path):
    return spark.read.option("header", "true").option("multiLine", "true").option("escape", '"').csv(str(path))


def read_postgres(spark, sql, schema):
    """Run a query on the ClassWizard database and return the rows as a Spark DataFrame."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute(sql).fetchall()
    return spark.createDataFrame(rows, schema=schema)


def run(spark):
    section("Step 1: Bronze layer - load source data")
    tables = {
        "catalog_courses": read_postgres(spark, COURSES_SQL, COURSES_SCHEMA),
        "catalog_links": read_postgres(spark, LINKS_SQL, LINKS_SCHEMA),
        "syllabus_triples": read_csv(spark, SYLLABI_CSV),
    }
    for name, filename in ONET_FILES.items():
        tables[name] = read_csv(spark, ONET_DIR / filename)

    for name, df in tables.items():
        df = df.toDF(*[snake_case(c) for c in df.columns]).withColumn("_ingested_at", F.current_timestamp())
        stored = write_table(df, "bronze", name)
        print(f"  bronze.{name:<26} {stored.count():>8,} rows")
