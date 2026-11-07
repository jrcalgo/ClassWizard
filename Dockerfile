# Starts the stack in docker-compose.yml, which builds:
#   backend/Dockerfile  (API, catalog CLI, Poppler 25.07.0, sentence-transformers)
#   frontend/Dockerfile
# Postgres (pgvector) and Redis are separate images. The catalog database is
# kept in the pgdata volume. docker compose down keeps that volume;
# docker compose down -v drops it. Redis stays empty until the next boot.
# The catalog zip is mounted at /data/dataset from
# data/_datasets/uncc-courses/catalog/dataset (undergraduate-catalog-2026-2027.zip).
# O*NET CSVs are mounted at /data/onet. First boot unzips the catalog, builds
# JSON under data/catalog_out, and loads Postgres. Later boots skip the catalog
# when the zip's SHA-256 is already stored in ingest_runs. O*NET, programs, and
# syllabi are loaded again on every boot.
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
