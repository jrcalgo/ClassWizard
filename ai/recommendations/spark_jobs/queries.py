"""Spark SQL queries on the Silver and Gold tables."""

from spark_jobs.session import read_table, section

CAREER = "15-2051.00"  # Data Scientists

TOP_COURSES_SQL = f"""
    SELECT c.course_code,
           COALESCE(c.title, '(syllabus only)') AS title,
           c.level,
           r.rating,
           r.doc_sim,
           r.term_score,
           r.n_matches
    FROM ratings r
    JOIN courses c ON c.course_code = r.course_code
    WHERE r.soc_code = '{CAREER}'
    ORDER BY r.rating DESC
    LIMIT 10
"""

IN_DEMAND_TECH_SQL = """
    SELECT c.subject,
           COUNT(DISTINCT t.term_key)    AS in_demand_technologies,
           COUNT(DISTINCT c.course_code) AS courses_covering_them,
           MIN(t.term)                   AS example
    FROM course_concepts cc
    JOIN term_links l           ON l.course_term = cc.term_key
    JOIN career_technologies t  ON t.term_key = l.onet_term
    JOIN courses c              ON c.course_code = cc.course_code
    WHERE t.in_demand
    GROUP BY c.subject
    ORDER BY in_demand_technologies DESC, courses_covering_them DESC
    LIMIT 10
"""


def run(spark):
    section("Step 4: Spark SQL on Silver and Gold")
    read_table(spark, "silver", "courses").createOrReplaceTempView("courses")
    read_table(spark, "silver", "course_concepts").createOrReplaceTempView("course_concepts")
    read_table(spark, "silver", "career_technologies").createOrReplaceTempView("career_technologies")
    read_table(spark, "gold", "term_links").createOrReplaceTempView("term_links")
    read_table(spark, "gold", "ratings").createOrReplaceTempView("ratings")

    print(f"Query 1 - Which courses fit Data Scientists ({CAREER}) best?")
    spark.sql(TOP_COURSES_SQL).show(truncate=False)

    print("Query 2 - Which subjects cover the most in-demand technologies in their syllabi?")
    spark.sql(IN_DEMAND_TECH_SQL).show(truncate=False)
