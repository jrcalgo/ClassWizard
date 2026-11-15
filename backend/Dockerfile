# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    UV_SYSTEM_PYTHON=1

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update \
 && apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      curl \
      bzip2 \
      postgresql-client \
 && rm -rf /var/lib/apt/lists/*

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Pinned micromamba binary only. The Poppler install below uses an explicit
# package list, so this build does not solve conda-forge.
ARG TARGETARCH
ARG MICROMAMBA_VERSION=2.3.2
RUN set -eu \
 && case "$TARGETARCH" in \
      amd64) mamba_arch=linux-64 ;; \
      arm64) mamba_arch=linux-aarch64 ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl -fsSL "https://micro.mamba.pm/api/micromamba/${mamba_arch}/${MICROMAMBA_VERSION}" \
      | tar -xj -C /usr/local/bin --strip-components=1 bin/micromamba \
 && micromamba --version

COPY docker/poppler/linux-64.explicit docker/poppler/linux-aarch64.explicit /tmp/poppler/
RUN --mount=type=cache,target=/opt/mamba-root/pkgs,sharing=locked \
    set -eu \
 && case "$TARGETARCH" in \
      amd64) poppler_arch=linux-64 ;; \
      arm64) poppler_arch=linux-aarch64 ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && MAMBA_ROOT_PREFIX=/opt/mamba-root \
    micromamba create -y -p /opt/poppler --file "/tmp/poppler/${poppler_arch}.explicit" \
 && for path in /opt/mamba-root/*; do \
      [ "$(basename "$path")" = "pkgs" ] || rm -rf "$path"; \
    done \
 && rm -f /usr/local/bin/micromamba \
 && rm -rf /tmp/poppler \
 && ln -s /opt/poppler/bin/pdftotext /usr/local/bin/pdftotext \
 && pdftotext -v 2>&1 | grep -q "version 25.07.0"

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

# Java 17 for PySpark (spark_jobs/). procps: the Spark launch script calls ps.
# Installed before the lock and app layers so code changes don't rebuild it.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jre-headless procps \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU torch is pinned in each lock (torch==…+cpu). The lock's indexes keep
# a later resolve from replacing it with the CUDA wheel on PyPI. One lock per
# architecture; TARGETARCH picks the file (see backend/requirements.in).
COPY backend/requirements.linux-64.lock /tmp/requirements.linux-64.lock
COPY backend/requirements.linux-aarch64.lock /tmp/requirements.linux-aarch64.lock
RUN --mount=type=cache,target=/root/.cache/uv \
    set -eu \
 && case "$TARGETARCH" in \
      amd64) lock=linux-64 ;; \
      arm64) lock=linux-aarch64 ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && uv pip install --system \
      --index-url https://download.pytorch.org/whl/cpu \
      --extra-index-url https://pypi.org/simple \
      --index-strategy unsafe-best-match \
      -r "/tmp/requirements.${lock}.lock" \
 && rm -f /tmp/requirements.linux-64.lock /tmp/requirements.linux-aarch64.lock

ENV HF_HOME=/opt/hf \
    SENTENCE_TRANSFORMERS_HOME=/opt/sentence-transformers
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY backend /app/backend
COPY ai /app/ai
COPY spark_jobs /app/spark_jobs
COPY data/__init__.py /app/data/__init__.py
COPY data/degreeworks /app/data/degreeworks
COPY data/uncc-courses/catalog/pyproject.toml /tmp/catalog/pyproject.toml
COPY data/uncc-courses/catalog/pipeline/ /tmp/catalog/catalog_pipeline/
COPY data/uncc-courses/catalog/tests/ /tmp/catalog/tests/
COPY data/onet/etl_pipeline.py /app/data/onet/etl_pipeline.py
COPY data/onet/schemas.py /app/data/onet/schemas.py
COPY ["docs/Major&courses/major_requirements.sql", "/app/sql/major_requirements.sql"]
COPY ["docs/Major&courses/classes.sql", "/app/sql/classes.sql"]
RUN python3 -m pip install --no-cache-dir --no-deps /tmp/catalog \
 && rm -rf /tmp/catalog

COPY backend/start.sh /usr/local/bin/start-backend.sh
RUN tr -d '\r' < /usr/local/bin/start-backend.sh > /usr/local/bin/start-backend.sh.clean \
 && mv /usr/local/bin/start-backend.sh.clean /usr/local/bin/start-backend.sh \
 && chmod 755 /usr/local/bin/start-backend.sh \
 && mkdir -p /data/out /data/dataset

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=600s --retries=30 \
    CMD python3 -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()==b'OK'"

ENTRYPOINT ["/bin/bash", "/usr/local/bin/start-backend.sh"]
