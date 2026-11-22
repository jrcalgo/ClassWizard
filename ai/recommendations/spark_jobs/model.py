"""Spark ML: ALS recommender on the career x course ratings.

user = career, item = course, label = rating. 80/20 split, RMSE on the test set.
"""

from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.recommendation import ALS
from pyspark.sql import functions as F

from ai.recommendations.spark_jobs.session import LAKE_DIR, read_table, section, write_table

SEED = 42
RANKS = [8, 16, 32]
REG_PARAMS = [0.01, 0.05, 0.1]
SAMPLE_CAREERS = ["15-2051.00", "15-1252.00", "13-2011.00"]  # data scientists, software developers, accountants


def make_als(rank, reg_param):
    # coldStartStrategy="drop" skips pairs whose career or course was not in the training data.
    return ALS(userCol="user_id", itemCol="item_id", ratingCol="rating",
               rank=rank, regParam=reg_param, maxIter=10, coldStartStrategy="drop", seed=SEED)


def rmse(predictions, prediction_col="prediction"):
    evaluator = RegressionEvaluator(metricName="rmse", labelCol="rating", predictionCol=prediction_col)
    return evaluator.evaluate(predictions)


def run(spark):
    section("Step 5: Spark ML - ALS recommender (careers x courses)")
    ratings = read_table(spark, "gold", "ratings")

    train, test = ratings.randomSplit([0.8, 0.2], seed=SEED)
    train.cache()
    test.cache()
    print(f"Ratings: {ratings.count():,}   train: {train.count():,}   test: {test.count():,}")

    # Pick rank and regParam on a validation split, so the test set is only used once.
    print("Tuning on a validation split of the training data:")
    fit_part, validation = train.randomSplit([0.75, 0.25], seed=SEED)
    best_score, best_rank, best_reg = None, None, None
    for rank in RANKS:
        for reg_param in REG_PARAMS:
            score = rmse(make_als(rank, reg_param).fit(fit_part).transform(validation))
            print(f"  rank={rank:<3} regParam={reg_param:<5} validation RMSE = {score:.4f}")
            if best_score is None or score < best_score:
                best_score, best_rank, best_reg = score, rank, reg_param
    print(f"Best: rank={best_rank}, regParam={best_reg}")

    model = make_als(best_rank, best_reg).fit(train)
    test_predictions = model.transform(test)

    # Baselines: always predict the overall average, or the course's own average.
    global_mean = train.agg(F.avg("rating")).first()[0]
    course_means = train.groupBy("item_id").agg(F.avg("rating").alias("course_mean"))
    baseline = test.join(course_means, "item_id").withColumn("global_mean", F.lit(global_mean))

    print()
    print(f"Test RMSE (ALS):                  {rmse(test_predictions):.4f}")
    print(f"Baseline RMSE (course average):   {rmse(baseline, 'course_mean'):.4f}")
    print(f"Baseline RMSE (overall average):  {rmse(baseline, 'global_mean'):.4f}")
    print()

    # The score is the raw ALS prediction. Capping it at 5 makes the best courses tie.
    predictions = write_table(
        model.transform(ratings).select("soc_code", "course_code",
                                        F.round("prediction", 3).alias("als_score"),
                                        F.col("rating").alias("hybrid_rating")),
        "gold", "predictions")
    print(f"  gold.predictions     {predictions.count():>10,} rows   (a score for every career x course pair)")
    print()

    careers = read_table(spark, "silver", "careers").select("soc_code", F.col("title").alias("career"))
    courses = read_table(spark, "silver", "courses").select(
        "course_code", F.coalesce("title", F.lit("(syllabus only)")).alias("course_title"))

    print("Sample predictions on test pairs:")
    (test_predictions.join(careers, "soc_code").join(courses, "course_code")
     .select("career", "course_code", "course_title", "rating", F.round("prediction", 3).alias("prediction"))
     .orderBy(F.rand(SEED)).show(10, truncate=40))

    named = predictions.join(careers, "soc_code").join(courses, "course_code")
    for soc_code in SAMPLE_CAREERS:
        print(f"Top 5 recommended courses for {soc_code}:")
        (named.filter(F.col("soc_code") == soc_code).orderBy(F.desc("als_score"))
         .select("career", "course_code", "course_title", "als_score", "hybrid_rating").show(5, truncate=40))

    model.write().overwrite().save(str(LAKE_DIR / "models" / "als_career_course"))
