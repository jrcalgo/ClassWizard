# Starts the stack in docker-compose.yml, which builds:
#   backend/Dockerfile  (Postgres with pgvector, Redis, and the catalog CLI)
#   frontend/Dockerfile
# The catalog dataset is mounted into the backend container at /data/dataset
# from data/_datasets/uncc-courses/catalog/dataset.
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
