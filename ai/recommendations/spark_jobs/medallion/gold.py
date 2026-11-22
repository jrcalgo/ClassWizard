"""Gold layer: a 0-5 rating for every (career, course) pair, the input for ALS.

ClassWizard keeps no student history, so careers play the "user" role. The
rating combines two signals:
    doc_sim     how close the course text is to the career text
    term_score  how many of the career's important skills the syllabus covers
"""

import numpy as np
from pyspark.ml.feature import StringIndexer
from pyspark.sql import functions as F

from ai.recommendations.spark_jobs.session import read_table, section, write_table

MIN_IMPORTANCE = 3.0   # O*NET importance runs 1-5; 3 and up counts as important
MIN_SIMILARITY = 0.55  # a syllabus concept this close to a skill name counts as a match

# Each signal becomes a percentile within the career, so careers are comparable.
# Courses with no syllabus data are rated on text similarity alone.
RATING_SQL = """
    WITH signals AS (
        SELECT d.catalog_name, d.soc_code, d.course_code, d.doc_sim, c.has_syllabus,
               CASE WHEN c.has_syllabus THEN COALESCE(e.term_score, 0) END AS term_score,
               COALESCE(e.n_matches, 0) AS n_matches
        FROM doc_similarity d
        JOIN courses c ON c.course_code = d.course_code AND c.catalog_name = d.catalog_name
        LEFT JOIN evidence e ON e.soc_code = d.soc_code AND e.course_code = d.course_code AND e.catalog_name = d.catalog_name
    ),
    percentiles AS (
        SELECT *,
               PERCENT_RANK() OVER (PARTITION BY catalog_name, soc_code ORDER BY doc_sim) AS p_doc,
               PERCENT_RANK() OVER (PARTITION BY catalog_name, soc_code, has_syllabus ORDER BY term_score) AS p_term
        FROM signals
    ),
    combined AS (
        SELECT *, CASE WHEN has_syllabus THEN (p_doc + p_term) / 2 ELSE p_doc END AS hybrid
        FROM percentiles
    )
    SELECT catalog_name, soc_code, course_code,
           ROUND(doc_sim, 4) AS doc_sim, ROUND(term_score, 4) AS term_score, n_matches,
           ROUND(5 * PERCENT_RANK() OVER (PARTITION BY catalog_name, soc_code ORDER BY hybrid), 3) AS rating
    FROM combined
"""


def embed(texts):
    """MiniLM vectors of length 1, one row per text (the model the rest of ClassWizard uses)."""
    from ai.nlp.embeddings.sentence_transformer import get_model

    return get_model().encode(texts, batch_size=128, normalize_embeddings=True, show_progress_bar=False)


def build_career_terms(career_skills, career_technologies):
    """The skills, knowledge areas, and technologies that matter to each career, with a weight."""
    skills = (
        career_skills.filter(F.col("importance") >= MIN_IMPORTANCE)
        .select("soc_code", "term_key", "term", "kind", ((F.col("importance") - 1) / 4).alias("weight"))
    )
    technologies = career_technologies.select(
        "soc_code", "term_key", "term", F.lit("technology").alias("kind"),
        (0.4 + 0.3 * F.col("hot").cast("int") + 0.3 * F.col("in_demand").cast("int")).alias("weight"),
    )
    return skills.unionByName(technologies).dropDuplicates(["soc_code", "term_key"])


def similar_terms(concepts, concept_vectors, skills, skill_vectors):
    """(concept, skill, similarity) for every pair at or above MIN_SIMILARITY."""
    similarity = concept_vectors @ skill_vectors.T
    rows, cols = np.where(similarity >= MIN_SIMILARITY)
    return [(concepts[r], skills[c], float(similarity[r, c])) for r, c in zip(rows, cols)]


def build_term_links(spark, concepts, career_terms):
    """Link syllabus concepts to O*NET terms.

    Skill and knowledge names are matched by meaning. Technologies are product
    names, so they must match exactly: by meaning, "painting" matches "Microsoft Paint".
    """
    concept_list = [r.term_key for r in concepts.select("term_key").distinct().collect()]
    skill_list = [r.term_key for r in
                  career_terms.filter(F.col("kind") != "technology").select("term_key").distinct().collect()]
    skill_links = spark.createDataFrame(
        similar_terms(concept_list, embed(concept_list), skill_list, embed(skill_list)),
        "course_term string, onet_term string, similarity double",
    )
    technologies = career_terms.filter(F.col("kind") == "technology").select("term_key").distinct()
    technology_links = (
        concepts.select("term_key").distinct().join(technologies, "term_key")
        .select(F.col("term_key").alias("course_term"), F.col("term_key").alias("onet_term"),
                F.lit(1.0).alias("similarity"))
    )
    return skill_links.unionByName(technology_links)


def contributing_matches(concepts, term_links, career_terms):
    """Exact unaggregated scoring contributions, including multiplicity."""
    return (
        concepts.alias("concept").join(term_links, F.col("concept.term_key") == term_links.course_term)
        .join(career_terms.select("soc_code", F.col("term_key").alias("onet_term"),
                                 F.col("term").alias("career_term"), "kind", "weight"), "onet_term")
        .withColumn("points", F.col("confidence") * F.col("similarity") * F.col("weight"))
    )


def term_evidence(concepts, term_links, career_terms, courses):
    """Aggregate the same contributions exposed by explanation evidence."""
    matches = contributing_matches(concepts, term_links, career_terms)
    # Divide by sqrt(concepts) so a long syllabus does not win on length alone.
    return (
        matches.groupBy("soc_code", "course_code")
        .agg(F.sum("points").alias("points"), F.count("*").alias("n_matches"))
        .join(courses.select("catalog_name", "course_code", "n_concepts"), "course_code")
        .withColumn("term_score", F.col("points") / F.sqrt("n_concepts"))
        .select("catalog_name", "soc_code", "course_code", "term_score", "n_matches")
    )


def first_terms(df, key, limit):
    """{key: the first `limit` terms}, keeping the DataFrame's order."""
    grouped = {}
    for row in df.collect():
        grouped.setdefault(row[key], []).append(row["term"])
    return {k: terms[:limit] for k, terms in grouped.items()}


def doc_similarity(spark, courses, concepts, careers, career_skills, career_technologies):
    """Similarity between each course's text and each career's text."""
    topics = first_terms(concepts.orderBy("course_code", F.desc("confidence"), "term"), "course_code", 20)
    skills = first_terms(career_skills.orderBy("soc_code", F.desc("importance"), "term"), "soc_code", 10)
    technologies = first_terms(
        career_technologies.filter("hot OR in_demand").orderBy("soc_code", F.desc("in_demand"), "term"),
        "soc_code", 15)

    course_codes, course_texts = [], []
    for row in courses.orderBy("course_code").collect():
        parts = [row.course_code, row.title, row.description, "; ".join(topics.get(row.course_code, []))]
        course_codes.append((row.catalog_name, row.course_code))
        course_texts.append(". ".join(p for p in parts if p))

    soc_codes, career_texts = [], []
    for row in careers.orderBy("soc_code").collect():
        parts = [row.title, row.description, "; ".join(skills.get(row.soc_code, [])),
                 "; ".join(technologies.get(row.soc_code, []))]
        soc_codes.append(row.soc_code)
        career_texts.append(". ".join(p for p in parts if p))

    # The vectors have length 1, so the dot product is the cosine similarity.
    similarity = embed(course_texts) @ embed(career_texts).T
    rows = [(catalog, soc, code, float(similarity[i, j]))
            for j, soc in enumerate(soc_codes) for i, (catalog, code) in enumerate(course_codes)]
    return spark.createDataFrame(rows, "catalog_name string, soc_code string, course_code string, doc_sim double")


def add_als_ids(ratings):
    """ALS needs integer ids: careers become user_id, courses become item_id."""
    ratings = ratings.withColumn("course_identity", F.to_json(F.struct("catalog_name", "course_code")))
    for column, id_column in [("soc_code", "user_id"), ("course_identity", "item_id")]:
        indexer = StringIndexer(inputCol=column, outputCol=id_column)
        ratings = indexer.fit(ratings).transform(ratings).withColumn(id_column, F.col(id_column).cast("int"))
    return ratings


def run(spark):
    section("Step 3: Gold layer - career x course ratings")
    courses = read_table(spark, "silver", "courses")
    concepts = read_table(spark, "silver", "course_concepts")
    careers = read_table(spark, "silver", "careers")
    career_skills = read_table(spark, "silver", "career_skills")
    career_technologies = read_table(spark, "silver", "career_technologies")

    career_terms = write_table(build_career_terms(career_skills, career_technologies), "gold", "career_terms")
    term_links = write_table(build_term_links(spark, concepts, career_terms), "gold", "term_links")
    similarity = write_table(
        doc_similarity(spark, courses, concepts, careers, career_skills, career_technologies),
        "gold", "doc_similarity")

    similarity.createOrReplaceTempView("doc_similarity")
    courses.createOrReplaceTempView("courses")
    term_evidence(concepts, term_links, career_terms, courses).createOrReplaceTempView("evidence")
    rated = spark.sql(RATING_SQL).cache()
    ratings = write_table(add_als_ids(rated), "gold", "ratings")

    print(f"  gold.career_terms    {career_terms.count():>10,} rows")
    print(f"  gold.term_links      {term_links.count():>10,} rows")
    print(f"  gold.doc_similarity  {similarity.count():>10,} rows")
    print(f"  gold.ratings         {ratings.count():>10,} rows   "
          f"({careers.count():,} careers x {courses.count():,} courses)")
    print()
    print("  Rating summary:")
    ratings.select("doc_sim", "term_score", "n_matches", "rating").describe().show()
    rated.unpersist()
