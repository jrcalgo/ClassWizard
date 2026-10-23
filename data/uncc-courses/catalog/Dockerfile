# Image for the catalog_pipeline package (PDF print-outs -> validated JSON).
# Build context is the repo root (set in docker-compose.yml).

# Stage 1 exists only to supply the micromamba binary (a small conda installer).
FROM mambaorg/micromamba:2.3.2 AS micromamba

FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# pdftotext: extract.py runs it as a subprocess, so pip cannot provide it.
# The parser was fitted to poppler 25.07.0's output. No Debian release ships
# that version (trixie has 25.03.0), so it comes from conda-forge, the same
# source the common Windows poppler builds are repackaged from.
# "*_1" pins the build number as well, and matches on amd64 and arm64.
ARG POPPLER_SPEC="poppler=25.07.0=*_1"
COPY --from=micromamba /bin/micromamba /usr/local/bin/micromamba
RUN MAMBA_ROOT_PREFIX=/tmp/mamba micromamba create -y -q -p /opt/poppler \
        -c conda-forge --override-channels "$POPPLER_SPEC" \
 && rm -rf /tmp/mamba /usr/local/bin/micromamba \
 && ln -s /opt/poppler/bin/pdftotext /usr/local/bin/pdftotext \
 && pdftotext -v 2>&1 | grep -q "version 25.07.0"

WORKDIR /app

# Dependencies declared in data/uncc-courses/catalog/pyproject.toml.
RUN pip install --no-cache-dir "pdfplumber>=0.10" "jsonschema>=4.18"

# Package sources live in data/uncc-courses/catalog. The import name is
# catalog_pipeline; the source directory is pipeline/.
COPY data/uncc-courses/catalog/pyproject.toml ./
COPY data/uncc-courses/catalog/pipeline/ catalog_pipeline/
COPY data/uncc-courses/catalog/tests/ tests/
RUN pip install --no-cache-dir --no-deps .

# Run as an ordinary user (uid 1000 matches the usual first Linux account,
# so files written to bind mounts are owned by you).
RUN useradd --uid 1000 --create-home app && mkdir -p /data/out && chown app /data/out
USER app

ENTRYPOINT ["python", "-m", "catalog_pipeline"]
CMD ["--help"]
