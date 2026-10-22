



# Services
Catalog_Pipeline
- Built in Python 3.12, locally from `docker/catalog/pipeline/Dockerfile`
- Requires no port, mainly a single instance job.
- Starts via `docker compose run --rm catalog-pipeline`
- The PDFs are manually saved via Microsoft to PDF from the UNCC Course Catalog. Refer to `catalog_pipeline_tool` to see how it was done.