FROM mambaorg/micromamba:2.3.2 AS micromamba

FROM pgvector/pgvector:pg16

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip python3-venv redis-server \
 && rm -rf /var/lib/apt/lists/*

ARG POPPLER_SPEC="poppler=25.07.0=*_1"
COPY --from=micromamba /bin/micromamba /usr/local/bin/micromamba
RUN MAMBA_ROOT_PREFIX=/tmp/mamba micromamba create -y -q -p /opt/poppler \
        -c conda-forge --override-channels "$POPPLER_SPEC" \
 && rm -rf /tmp/mamba /usr/local/bin/micromamba \
 && ln -s /opt/poppler/bin/pdftotext /usr/local/bin/pdftotext \
 && pdftotext -v 2>&1 | grep -q "version 25.07.0"

WORKDIR /app

RUN pip3 install --no-cache-dir --break-system-packages \
        "fastapi" "uvicorn" "psycopg[binary]" "redis" \
        "pdfplumber>=0.10" "jsonschema>=4.18" \
        "pandas" "pydantic" "litellm" "python-multipart" "sentence-transformers"

COPY backend /app/backend
COPY data/__init__.py /app/data/__init__.py
COPY data/degreeworks /app/data/degreeworks
COPY data/uncc-courses/catalog/pyproject.toml /tmp/catalog/pyproject.toml
COPY data/uncc-courses/catalog/pipeline/ /tmp/catalog/catalog_pipeline/
COPY data/uncc-courses/catalog/tests/ /tmp/catalog/tests/
COPY data/onet/etl_pipeline.py /app/data/onet/etl_pipeline.py
COPY data/onet/schemas.py /app/data/onet/schemas.py
COPY ["docs/Major&courses/major_requirements.sql", "/app/sql/major_requirements.sql"]
COPY ["docs/Major&courses/classes.sql", "/app/sql/classes.sql"]
RUN pip3 install --no-cache-dir --break-system-packages --no-deps /tmp/catalog \
 && rm -rf /tmp/catalog

COPY init.sql /docker-entrypoint-initdb.d/init.sql
COPY backend/start.sh /usr/local/bin/start-backend.sh
RUN tr -d '\r' < /usr/local/bin/start-backend.sh > /usr/local/bin/start-backend.sh.clean \
 && mv /usr/local/bin/start-backend.sh.clean /usr/local/bin/start-backend.sh \
 && chmod 755 /usr/local/bin/start-backend.sh \
 && mkdir -p /data/out /data/dataset

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=600s --retries=30 \
    CMD python3 -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()==b'OK'"

ENTRYPOINT ["/bin/bash", "/usr/local/bin/start-backend.sh"]
