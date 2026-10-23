# Starts the stack in docker-compose.yml, which builds:
#   backend/Dockerfile  (Postgres with pgvector, Redis, and the catalog CLI)
#   frontend/Dockerfile
# The catalog zip is mounted at /data/dataset from
# data/_datasets/uncc-courses/catalog/dataset (undergraduate-catalog-2026-2027.zip).
# O*NET CSVs are mounted at /data/onet. First boot unzips the catalog, builds
# JSON under data/catalog_out, and loads Postgres. Later boots skip a release
# already recorded in ingest_runs.
#
#   docker build -t classwizard .
#   docker run --rm \
#     -v /var/run/docker.sock:/var/run/docker.sock \
#     -v "$PWD:$PWD" \
#     -w "$PWD" \
#     classwizard
FROM docker:27-cli

ENV POSTGRES_DB=classwizard \
    POSTGRES_USER=classwizard \
    REDIS_URL=redis://redis:6379/0 \
    COMPOSE_PROJECT_NAME=classwizard \
    CATALOG_DATASET_DIR=./data/_datasets/uncc-courses/catalog/dataset

ENTRYPOINT ["docker", "compose"]
CMD ["up", "--build"]
