"""Silver layer: clean, type, de-duplicate, and join the Bronze tables."""

from pyspark.sql import functions as F

from ai.recommendations.spark_jobs.session import read_table, section, term_key, write_table

COURSE_CODE = r"^[A-Z]{2,5} \d{4}[A-Z]{0,2}$"
DEGREE_JOB_ZONES = [4, 5]  # bachelor's degree or more


def course_code(column):
    """'itsc  3160 ' or 'ITSC_3160' -> 'ITSC 3160'."""
    return F.upper(F.trim(F.regexp_replace(column, r"[\s_]+", " ")))


def clean_catalog_courses(bronze_courses, bronze_links):
    """Catalog courses, one row per code, with a prerequisite count."""
    prereqs = (
        bronze_links.filter(F.col("kind") == "prerequisite")
        .select(course_code(F.col("course_code")).alias("course_code"), "target_code")
        .distinct()
        .groupBy("course_code").count()
        .withColumnRenamed("count", "n_prereqs")
    )
    return (
        bronze_courses
        .withColumn("course_code", course_code(F.col("code")))
        .filter(F.col("course_code").rlike(COURSE_CODE))
        .withColumn("title", F.trim("title"))
        .withColumn("description", F.trim("description"))
        .withColumn("credits", F.col("credit_min").cast("int"))
        .dropDuplicates(["course_code"])
        .join(prereqs, "course_code", "left")
        .select("course_code", "title", "description", "credits", "n_prereqs")
    )


def clean_course_concepts(bronze_triples):
    """One row per (course, concept), from the 'course covers concept' triples."""
    return (
        bronze_triples.filter(F.col("predicate") == "covers")
        .withColumn("course_code", course_code(F.col("subject")))
        .filter(F.col("course_code").rlike(COURSE_CODE))
        .withColumn("term", F.trim("object"))
        .withColumn("term_key", term_key(F.col("object")))
        .withColumn("confidence", F.col("confidence").cast("double"))
        .select("course_code", "term", "term_key", "confidence")
        .dropna()
        .filter(F.col("term_key") != "")
        .dropDuplicates(["course_code", "term_key"])
    )


def build_courses(catalog_courses, course_concepts):
    """Catalog courses and syllabus courses joined by course code."""
    syllabus = course_concepts.groupBy("course_code").count().withColumnRenamed("count", "n_concepts")
    number = F.regexp_extract("course_code", r" (\d{4})", 1).cast("int")
    return (
        catalog_courses.join(syllabus, "course_code", "outer")
        .withColumn("subject", F.split("course_code", " ").getItem(0))
        .withColumn("level", F.when(number >= 5000, "graduate").otherwise("undergraduate"))
        .withColumn("in_catalog", F.col("title").isNotNull())
        .withColumn("has_syllabus", F.col("n_concepts").isNotNull())
        .fillna(0, subset=["n_concepts", "n_prereqs"])
        .select("course_code", "subject", "level", "title", "description", "credits",
                "n_prereqs", "n_concepts", "in_catalog", "has_syllabus")
    )


def clean_careers(bronze_occupations, bronze_job_zones):
    """Occupations that need a bachelor's degree or more (job zones 4-5)."""
    zones = (
        bronze_job_zones
        .select(F.trim("o_net_soc_code").alias("soc_code"), F.col("job_zone").cast("int").alias("job_zone"))
        .filter(F.col("job_zone").isin(DEGREE_JOB_ZONES))
        .dropDuplicates(["soc_code"])
    )
    return (
        bronze_occupations
        .select(F.trim("o_net_soc_code").alias("soc_code"), F.trim("title").alias("title"),
                F.trim("description").alias("description"))
        .dropna(subset=["soc_code", "title"])
        .dropDuplicates(["soc_code"])
        .join(zones, "soc_code")
    )


def clean_career_skills(bronze_skills, careers):
    """Importance (1-5) of each skill and knowledge area per career."""
    return (
        bronze_skills
        .filter(F.col("scale_id") == "IM")
        .filter(F.coalesce(F.col("recommend_suppress"), F.lit("N")) != "Y")
        .select(F.trim("o_net_soc_code").alias("soc_code"), F.trim("element_name").alias("term"), "kind",
                F.col("data_value").cast("double").alias("importance"))
        .dropna()
        .withColumn("term_key", term_key(F.col("term")))
        .join(careers.select("soc_code"), "soc_code")
        .dropDuplicates(["soc_code", "term_key"])
    )


def clean_career_technologies(bronze_software, careers):
    """Software each career uses, one row per (career, technology)."""
    return (
        bronze_software
        .select(F.trim("o_net_soc_code").alias("soc_code"), F.trim("workplace_example").alias("term"),
                (F.col("hot_technology") == "Y").alias("hot"), (F.col("in_demand") == "Y").alias("in_demand"))
        .dropna()
        .withColumn("term_key", term_key(F.col("term")))
        .join(careers.select("soc_code"), "soc_code")
        .dropDuplicates(["soc_code", "term_key"])
    )


def run(spark):
    section("Step 2: Silver layer - clean, type, de-duplicate, join")
    catalog = clean_catalog_courses(read_table(spark, "bronze", "catalog_courses"),
                                    read_table(spark, "bronze", "catalog_links"))
    concepts = write_table(clean_course_concepts(read_table(spark, "bronze", "syllabus_triples")),
                           "silver", "course_concepts")
    courses = write_table(build_courses(catalog, concepts), "silver", "courses")
    careers = write_table(clean_careers(read_table(spark, "bronze", "onet_occupations"),
                                        read_table(spark, "bronze", "onet_job_zones")),
                          "silver", "careers")

    skills = (
        read_table(spark, "bronze", "onet_essential_skills")
        .unionByName(read_table(spark, "bronze", "onet_transferable_skills"))
        .withColumn("kind", F.lit("skill"))
        .unionByName(read_table(spark, "bronze", "onet_knowledge").withColumn("kind", F.lit("knowledge")))
    )
    career_skills = write_table(clean_career_skills(skills, careers), "silver", "career_skills")
    technologies = write_table(clean_career_technologies(read_table(spark, "bronze", "onet_software_skills"), careers),
                               "silver", "career_technologies")

    print(f"  silver.courses              {courses.count():>8,} rows   (catalog + syllabus)")
    print(f"  silver.course_concepts      {concepts.count():>8,} rows")
    print(f"  silver.careers              {careers.count():>8,} rows   (job zones 4-5)")
    print(f"  silver.career_skills        {career_skills.count():>8,} rows")
    print(f"  silver.career_technologies  {technologies.count():>8,} rows")
    print()
    print("  Courses by level and source:")
    courses.groupBy("level", "in_catalog", "has_syllabus").count().orderBy("level", "in_catalog").show()
