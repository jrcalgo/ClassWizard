"""Run the Spark pipeline: Bronze, Silver, Gold, Spark SQL, ALS, publish.

The backend runs it in the background on boot whenever the scores are missing
or older than the loaded data (see backend/start.sh). To run it by hand:
    docker compose exec backend sh -c "python3 -m ai.recommendations.spark_jobs.run_all | tee /data/lake/sprint4_results.txt"

Run only some steps:
    docker compose exec backend python3 -m ai.recommendations.spark_jobs.run_all --steps gold,queries

--check exits 0 when a run is needed and 1 when the scores are current.
"""

import argparse
import fcntl
import json
import os
import psycopg
import sys
import time

from ai.recommendations.spark_jobs.medallion import bronze, silver, gold
from ai.recommendations.spark_jobs import model, publish, queries
from ai.recommendations.spark_jobs.session import LAKE_DIR, get_spark, read_table, section

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
    unknown = set(chosen) - set(STEPS)
    if unknown:
        parser.error(f"Unknown steps: {sorted(unknown)}")
    LAKE_DIR.mkdir(parents=True, exist_ok=True)
    pipeline_lock = (LAKE_DIR / ".pipeline.lock").open("a")
    try:
        fcntl.flock(pipeline_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Spark rebuild already running; leaving its artifacts untouched")
        return

    if "bronze" in chosen:
        LAKE_DIR.mkdir(parents=True, exist_ok=True)
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            manifest = {"release": publish.inputs_key(conn), "scoring_version": publish.SCORING_VERSION}
        # Invalidate old provenance before overwriting any layer.
        publish.MANIFEST.unlink(missing_ok=True)
    else:
        manifest = json.loads(publish.MANIFEST.read_text())
    completed = set()
    spark = get_spark()
    print("Spark session started.")
    print(f"Spark version: {spark.version}")
    print(f"Spark UI:      {spark.sparkContext.uiWebUrl}  (http://localhost:4041 from the host)")

    for name, step in STEPS.items():
        if name in chosen:
            started = time.time()
            dependencies = {"silver": "bronze", "gold": "silver", "model": "gold", "publish": "model"}
            dependency = dependencies.get(name)
            if dependency and dependency not in completed:
                saved = json.loads((LAKE_DIR / f"{dependency}_manifest.json").read_text())
                if saved != manifest:
                    raise ValueError(f"Stale {dependency} artifacts; rebuild from Bronze")
            if name == "publish":
                publish.MANIFEST.write_text(json.dumps(manifest))
            stage_manifest = LAKE_DIR / f"{name}_manifest.json"
            ordered = ["bronze", "silver", "gold", "model", "publish"]
            if name in ordered:
                for downstream in ordered[ordered.index(name):]:
                    (LAKE_DIR / f"{downstream}_manifest.json").unlink(missing_ok=True)
            stage_manifest.unlink(missing_ok=True)
            step(spark)
            completed.add(name)
            stage_manifest.write_text(json.dumps(manifest))
            if name == "bronze":
                publish.MANIFEST.write_text(json.dumps(manifest))
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
