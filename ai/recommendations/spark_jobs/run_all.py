"""Run the Spark pipeline: Bronze, Silver, Gold, Spark SQL, ALS, publish.

The backend runs it in the background on boot whenever the scores are missing
or older than the loaded data (see backend/start.sh). To run it by hand:
    docker compose exec backend sh -c "python3 -m spark_jobs.run_all | tee /data/lake/sprint4_results.txt"

Run only some steps:
    docker compose exec backend python3 -m spark_jobs.run_all --steps gold,queries

--check exits 0 when a run is needed and 1 when the scores are current.
"""

import argparse
import sys
import time

from spark_jobs import bronze, gold, model, publish, queries, silver
from spark_jobs.session import LAKE_DIR, get_spark, read_table, section

TABLES = {
    "bronze": ["catalog_courses", "catalog_links", "syllabus_triples", "onet_occupations", "onet_job_zones",
               "onet_essential_skills", "onet_transferable_skills", "onet_knowledge", "onet_software_skills"],
    "silver": ["courses", "course_concepts", "careers", "career_skills", "career_technologies"],
    "gold": ["career_terms", "term_links", "doc_similarity", "ratings", "predictions"],
}

STEPS = {
    "bronze": bronze.run,
    "silver": silver.run,
    "gold": gold.run,
    "queries": queries.run,
    "model": model.run,
    "publish": publish.run,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", default=",".join(STEPS), help="comma-separated: " + ", ".join(STEPS))
    parser.add_argument("--check", action="store_true", help="exit 0 if a run is needed, 1 if scores are current")
    args = parser.parse_args()
    if args.check:
        current = publish.is_current()
        print("spark scores are current" if current else "spark scores missing or out of date")
        sys.exit(1 if current else 0)
    chosen = args.steps.split(",")

    spark = get_spark()
    print("Spark session started.")
    print(f"Spark version: {spark.version}")
    print(f"Spark UI:      {spark.sparkContext.uiWebUrl}  (http://localhost:4041 from the host)")

    for name, step in STEPS.items():
        if name in chosen:
            started = time.time()
            step(spark)
            print(f"({name} took {time.time() - started:.0f} seconds)")

    section("Record counts per layer")
    for layer, names in TABLES.items():
        total = 0
        for name in names:
            if (LAKE_DIR / layer / name).is_dir():
                count = read_table(spark, layer, name).count()
                total += count
                print(f"  {layer}.{name:<26} {count:>10,}")
        print(f"  {layer.upper()} total: {total:,} rows")
        print()
    spark.stop()


if __name__ == "__main__":
    main()
