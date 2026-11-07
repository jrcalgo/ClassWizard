"""Load catalog JSON, raw O*NET CSVs, and program SQL into Postgres."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

CATALOG_RELEASE = "Undergraduate 2026-2027"
ONET_RELEASE = "db_31_0"
PDF_PATTERN = __import__("re").compile(r"pg\d+\.pdf$", __import__("re").IGNORECASE)

DATASET_DIR = Path(os.environ.get("CATALOG_DATASET_DIR", "/data/dataset"))
CATALOG_ZIP = DATASET_DIR / "undergraduate-catalog-2026-2027.zip"
OUT_DIR = Path(os.environ.get("CATALOG_OUT_DIR", "/data/out"))
PDF_ROOT = OUT_DIR / "pdfs"
CATALOG_STAMP = OUT_DIR / "catalog.sha256"
ONET_DIR = Path(os.environ.get("ONET_DIR", "/data/onet/raw_onet_data/db_31_0_csv"))
SQL_DIR = Path(os.environ.get("PROGRAM_SQL_DIR", "/app/sql"))
SCHEMA_SQL = Path(__file__).resolve().parents[2] / "schema.sql"
SYLLABI_RELEASE = "v2"
SYLLABI_DIR = Path(os.environ.get("SYLLABI_DIR", "/data/syllabi"))

REQUISITE_KIND = {
    "Prerequisite(s)": "prerequisite",
    "Corequisite(s)": "corequisite",
    "Pre- or Corequisite(s)": "pre_or_corequisite",
}


def main() -> None:
    ensure_pgpassword()
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.autocommit = True
        run_psql(SCHEMA_SQL)
        load_catalog(conn)
        load_onet(conn)
        load_programs(conn)
        # Syllabus triples are optional enrichment: a bad triples file must
        # not stop the API from starting. load_syllabi runs in its own
        # transaction, so a failure rolls back cleanly and leaves the other
        # tables intact.
        try:
            load_syllabi(conn)
        except psycopg.Error as exc:
            print(f"syllabi load failed, continuing without triples: {exc}", file=sys.stderr)
        # Embeddings power semantic search, but relational queries (courses,
        # prerequisites, programs, O*NET) still work without them. A failure
        # here is reported loudly and the API still starts; the next boot
        # retries only the rows that are still missing a vector.
        try:
            embed_text_chunks(conn)
        except Exception as exc:  # model files, memory, or database errors
            print(f"text_chunks embedding failed, semantic search unavailable: {exc!r}", file=sys.stderr)
        print_counts(conn)


def ensure_pgpassword() -> None:
    if os.environ.get("PGPASSWORD"):
        return
    parsed = urlparse(os.environ["DATABASE_URL"])
    if parsed.password:
        os.environ["PGPASSWORD"] = unquote(parsed.password)


def run_psql(sql_path: Path) -> None:
    parsed = urlparse(os.environ["DATABASE_URL"])
    subprocess.run(
        [
            "psql",
            "-h",
            parsed.hostname or "127.0.0.1",
            "-p",
            str(parsed.port or 5432),
            "-U",
            os.environ.get("POSTGRES_USER", "classwizard"),
            "-d",
            os.environ.get("POSTGRES_DB", "classwizard"),
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(sql_path),
        ],
        check=True,
        env=os.environ,
    )


def already_loaded(conn, source: str, release: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ingest_runs WHERE source = %s AND release = %s",
        (source, release),
    ).fetchone()
    return row is not None


def replace_ingest_run(conn, source: str, release: str) -> None:
    conn.execute("DELETE FROM ingest_runs WHERE source = %s", (source,))
    conn.execute(
        "INSERT INTO ingest_runs (source, release) VALUES (%s, %s)",
        (source, release),
    )


def catalog_fingerprint(path: Path) -> str:
    """SHA-256 of the catalog zip. A replaced or edited file gets a new hash."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_rows(conn, sql: str, rows: list[tuple]) -> None:
    if not rows:
        return
    with conn.cursor() as cur:
        with cur.copy(sql) as copy:
            for row in rows:
                copy.write_row(row)


def load_catalog(conn) -> None:
    if not CATALOG_ZIP.is_file():
        raise SystemExit(f"catalog zip not found: {CATALOG_ZIP}")
    digest = catalog_fingerprint(CATALOG_ZIP)
    if already_loaded(conn, "catalog", digest):
        print(f"catalog unchanged ({digest[:12]})")
        return
    pdf_dir = ensure_pdf_dir(digest)
    courses_path, edges_path = ensure_catalog_json(pdf_dir, digest)
    courses_doc = json.loads(courses_path.read_text(encoding="utf-8"))
    edges_doc = json.loads(edges_path.read_text(encoding="utf-8"))
    catalog_name = courses_doc.get("catalog") or CATALOG_RELEASE
    course_rows = []
    chunk_rows = []
    for course in courses_doc["courses"]:
        code = course["code"]
        title = course["title"]
        description = course.get("description") or ""
        credit = course.get("credit_hours") or {}
        requisites = course.get("requisites") or {}
        course_rows.append(
            (
                catalog_name,
                code,
                course["subject"],
                course["number"],
                title,
                course.get("section"),
                description,
                credit.get("min") if credit else None,
                credit.get("max") if credit else None,
                credit.get("raw") if credit else None,
                requisite_raw(requisites, "prerequisite"),
                requisite_raw(requisites, "corequisite"),
                requisite_raw(requisites, "pre_or_corequisite"),
            )
        )
        chunk_rows.append(
            (
                "course",
                code,
                f"{code} {title} {description}".strip(),
                json.dumps({"catalog": catalog_name, "code": code}),
            )
        )
    link_rows = []
    for edge in edges_doc.get("edges", []):
        kind = link_kind(edge)
        if kind is None:
            continue
        link_rows.append(
            (
                catalog_name,
                edge["source"],
                edge["target"],
                kind,
                edge.get("timing"),
                edge.get("evidence"),
                bool(edge.get("advisory_only")),
                edge.get("target_resolved"),
            )
        )
    with conn.transaction():
        conn.execute("DELETE FROM text_chunks WHERE source_type = 'course'")
        conn.execute("DELETE FROM course_links")
        conn.execute("DELETE FROM courses")
        copy_rows(
            conn,
            """
            COPY courses (
              catalog_name, code, subject, number, title, section, description,
              credit_min, credit_max, credit_raw, prerequisite_raw, corequisite_raw,
              pre_or_corequisite_raw
            ) FROM STDIN
            """,
            course_rows,
        )
        copy_rows(
            conn,
            """
            COPY course_links (
              catalog_name, course_code, target_code, kind, timing, evidence,
              advisory_only, target_resolved
            ) FROM STDIN
            """,
            link_rows,
        )
        copy_rows(
            conn,
            """
            COPY text_chunks (source_type, source_key, chunk_text, metadata)
            FROM STDIN
            """,
            chunk_rows,
        )
        replace_ingest_run(conn, "catalog", digest)
    print(f"loaded catalog {catalog_name}: {len(course_rows)} courses, {len(link_rows)} links")


def requisite_raw(requisites: dict, key: str) -> str | None:
    item = requisites.get(key) or {}
    raw = item.get("raw") if isinstance(item, dict) else None
    return raw or None


def link_kind(edge: dict) -> str | None:
    edge_type = edge.get("type")
    if edge_type == "requisite":
        return REQUISITE_KIND.get(edge.get("field") or "")
    if edge_type in ("crosslist", "exclusion"):
        return edge_type
    return None


def catalog_outputs_match(digest: str) -> bool:
    courses_path = OUT_DIR / "courses.json"
    edges_path = OUT_DIR / "edges.json"
    if not CATALOG_STAMP.is_file() or not courses_path.is_file() or not edges_path.is_file():
        return False
    if CATALOG_STAMP.read_text(encoding="utf-8").strip() != digest:
        return False
    return find_pdf_dir(PDF_ROOT) is not None


def clear_catalog_outputs() -> None:
    if PDF_ROOT.exists():
        shutil.rmtree(PDF_ROOT)
    for name in ("courses.json", "edges.json", "catalog.sha256"):
        path = OUT_DIR / name
        if path.is_file():
            path.unlink()


def ensure_pdf_dir(digest: str) -> Path:
    if catalog_outputs_match(digest):
        found = find_pdf_dir(PDF_ROOT)
        if found is not None:
            return found
    clear_catalog_outputs()
    PDF_ROOT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(CATALOG_ZIP) as archive:
        safe_extract(archive, PDF_ROOT)
    found = find_pdf_dir(PDF_ROOT)
    if found is None:
        raise SystemExit(f"no pgN.pdf files after unzipping {CATALOG_ZIP}")
    print(f"unzipped catalog pages to {found}")
    return found


def safe_extract(archive: zipfile.ZipFile, dest: Path) -> None:
    root = dest.resolve()
    for info in archive.infolist():
        target = (dest / info.filename).resolve()
        if root != target and root not in target.parents:
            raise SystemExit(f"unsafe path in catalog zip: {info.filename}")
    archive.extractall(dest)


def find_pdf_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    counts: Counter[Path] = Counter()
    for path in root.rglob("*"):
        if path.is_file() and PDF_PATTERN.search(path.name):
            counts[path.parent] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def ensure_catalog_json(pdf_dir: Path, digest: str) -> tuple[Path, Path]:
    courses_path = OUT_DIR / "courses.json"
    edges_path = OUT_DIR / "edges.json"
    if catalog_outputs_match(digest):
        return courses_path, edges_path
    print(f"building catalog JSON from {pdf_dir}")
    subprocess.run(
        [
            "python3",
            "-m",
            "catalog_pipeline",
            "build",
            "--pdf-dir",
            str(pdf_dir),
            "--catalog",
            CATALOG_RELEASE,
            "--out",
            str(OUT_DIR),
        ],
        check=True,
        env=os.environ,
    )
    if not courses_path.is_file() or not edges_path.is_file():
        raise SystemExit("catalog build did not write courses.json and edges.json")
    CATALOG_STAMP.write_text(digest + "\n", encoding="utf-8")
    return courses_path, edges_path


def load_onet(conn) -> None:
    occupations = read_occupations()
    skills = read_scored(ONET_DIR / "essential_skills.csv")
    knowledge = read_scored(ONET_DIR / "knowledge.csv")
    education = read_education()
    technologies = read_technologies()
    skill_names = sorted({name for _, _, name, _, _ in skills + knowledge})
    known_socs = {soc for soc, _, _ in occupations}
    skills = [row for row in skills if row[0] in known_socs]
    knowledge = [row for row in knowledge if row[0] in known_socs]
    education = [row for row in education if row[0] in known_socs]
    technologies = [row for row in technologies if row[0] in known_socs]
    with conn.transaction():
        conn.execute(
            "DELETE FROM text_chunks WHERE source_type IN ('occupation', 'skill')"
        )
        conn.execute("DELETE FROM occupation_skills")
        conn.execute("DELETE FROM occupation_knowledge")
        conn.execute("DELETE FROM occupation_education")
        conn.execute("DELETE FROM occupation_technologies")
        conn.execute("DELETE FROM skill_terms")
        conn.execute("DELETE FROM occupations")
        copy_rows(
            conn,
            "COPY occupations (soc_code, title, description) FROM STDIN",
            occupations,
        )
        copy_rows(
            conn,
            """
            COPY occupation_skills (soc_code, element_id, element_name, scale_id, score)
            FROM STDIN
            """,
            skills,
        )
        copy_rows(
            conn,
            """
            COPY occupation_knowledge (soc_code, element_id, element_name, scale_id, score)
            FROM STDIN
            """,
            knowledge,
        )
        copy_rows(
            conn,
            """
            COPY occupation_education (soc_code, element_id, category, percentage)
            FROM STDIN
            """,
            education,
        )
        copy_rows(
            conn,
            "COPY occupation_technologies (soc_code, name, hot_technology) FROM STDIN",
            technologies,
        )
        copy_rows(conn, "COPY skill_terms (name) FROM STDIN", [(name,) for name in skill_names])
        occupation_chunks = [
            (
                "occupation",
                soc,
                f"{title} {description}".strip(),
                json.dumps({"soc_code": soc}),
            )
            for soc, title, description in occupations
        ]
        skill_chunks = [
            ("skill", name, name, json.dumps({"name": name})) for name in skill_names
        ]
        copy_rows(
            conn,
            "COPY text_chunks (source_type, source_key, chunk_text, metadata) FROM STDIN",
            occupation_chunks + skill_chunks,
        )
        replace_ingest_run(conn, "onet", ONET_RELEASE)
    print(
        f"loaded onet {ONET_RELEASE}: {len(occupations)} occupations, "
        f"{len(skills)} skill scores, {len(skill_names)} skill names"
    )


def read_occupations() -> list[tuple]:
    path = ONET_DIR / "occupation_data.csv"
    rows = {}
    for record in read_csv(path):
        soc = (record.get("O*NET-SOC Code") or record.get("onetsoc_code") or "").strip()
        title = (record.get("Title") or record.get("title") or "").strip()
        if not soc or not title:
            continue
        description = (record.get("Description") or record.get("description") or "").strip()
        rows[soc] = (soc, title, description)
    if not rows:
        raise SystemExit(f"no occupations in {path}")
    return list(rows.values())


def read_scored(path: Path) -> list[tuple]:
    rows = []
    for record in read_csv(path):
        soc = (record.get("O*NET-SOC Code") or "").strip()
        element_id = (record.get("Element ID") or "").strip()
        name = (record.get("Element Name") or element_id).strip()
        scale = (record.get("Scale ID") or "").strip()
        score = number(record.get("Data Value"))
        if not soc or not element_id or not name or not scale or score is None:
            continue
        rows.append((soc, element_id, name, scale, score))
    if not rows:
        raise SystemExit(f"no scored rows in {path}")
    return rows


def read_education() -> list[tuple]:
    path = ONET_DIR / "education.csv"
    rows = []
    for record in read_csv(path):
        element_id = (record.get("Element ID") or "").strip()
        if not element_id.startswith(("2.D", "2.E")):
            continue
        soc = (record.get("O*NET-SOC Code") or "").strip()
        category = (record.get("Category") or "").strip()
        if not category:
            category = (record.get("Element Name") or element_id).strip()
        percentage = number(record.get("Data Value"))
        if not soc or percentage is None:
            continue
        rows.append((soc, element_id, category, percentage))
    if not rows:
        raise SystemExit(f"no education rows in {path}")
    return rows


def read_technologies() -> list[tuple]:
    path = ONET_DIR / "software_skills.csv"
    rows = []
    for record in read_csv(path):
        soc = (record.get("O*NET-SOC Code") or "").strip()
        name = (record.get("Workplace Example") or record.get("Example") or "").strip()
        if not soc or not name:
            continue
        hot = (record.get("Hot Technology") or "").strip().upper() == "Y"
        rows.append((soc, name, hot))
    if not rows:
        raise SystemExit(f"no technology rows in {path}")
    return rows


def read_csv(path: Path):
    if not path.is_file():
        raise SystemExit(f"missing O*NET file: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def number(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_programs(conn) -> None:
    run_psql(SQL_DIR / "major_requirements.sql")
    run_psql(SQL_DIR / "classes.sql")
    with conn.transaction():
        conn.execute("DELETE FROM program_courses")
        conn.execute("DELETE FROM programs")
        conn.execute(
            """
            INSERT INTO programs (name, min_gpa, credit_requirement)
            SELECT DISTINCT ON (major) major, minimum_gpa, credit_requirement
            FROM major_requirements
            WHERE major IS NOT NULL AND btrim(major) <> ''
            ORDER BY major, (minimum_gpa IS NULL), (credit_requirement IS NULL), id
            ON CONFLICT (name) DO NOTHING
            """
        )
        conn.execute(
            """
            INSERT INTO programs (name)
            SELECT DISTINCT major
            FROM classes
            WHERE major IS NOT NULL AND btrim(major) <> ''
            ON CONFLICT (name) DO NOTHING
            """
        )
        conn.execute(
            """
            INSERT INTO program_courses (program_name, course_code, course_title, credits)
            SELECT major, NULLIF(btrim(class_number), ''), class_name, credits
            FROM classes
            WHERE major IS NOT NULL AND btrim(major) <> ''
              AND class_name IS NOT NULL AND btrim(class_name) <> ''
            """
        )
        replace_ingest_run(conn, "programs", "major_courses_sql")
    print("loaded programs from Major&courses SQL")


def find_syllabi_json() -> Path | None:
    candidates = [
        SYLLABI_DIR / "valid_triples_with_embeddings.json",
        Path(__file__).resolve().parents[3] / "data" / "uncc-courses" / "syllabi" / "valid_triples_with_embeddings.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_syllabi(conn) -> None:
    json_path = find_syllabi_json()
    if not json_path:
        print("syllabus triples embedding JSON not found, skipping syllabi load")
        return
    records = json.loads(json_path.read_text(encoding="utf-8"))
    rows = []
    seen = set()
    for r in records:
        # Additions to avoid duplicate triples with the same triple_id and filename
        key = (r.get("triple_id", ""), r.get("filename") or None)
        if key in seen:
            continue
        seen.add(key)
        
        emb = r.get("embedding")
        emb_str = str(emb) if emb is not None else None
        rows.append(
            (
                r.get("triple_id", ""),
                r.get("subject", ""),
                r.get("subject_type", ""),
                r.get("subject_canonical_id") or None,
                r.get("predicate", ""),
                r.get("object", ""),
                r.get("object_type", ""),
                r.get("object_canonical_id") or None,
                float(r.get("confidence") or 0.9),
                r.get("evidence", ""),
                r.get("filename") or None,
                int(r["page_num"]) if r.get("page_num") else None,
                r.get("section_heading") or None,
                emb_str,
            )
        )
    with conn.transaction():
        conn.execute("DELETE FROM syllabus_triples")
        copy_rows(
            conn,
            """
            COPY syllabus_triples (
              triple_id, subject, subject_type, subject_canonical_id,
              predicate, object, object_type, object_canonical_id,
              confidence, evidence, filename, page_num, section_heading,
              embedding
            ) FROM STDIN
            """,
            rows,
        )
        replace_ingest_run(conn, "syllabi", SYLLABI_RELEASE)
    print(f"loaded syllabi {SYLLABI_RELEASE}: {len(rows)} triples with embeddings")


EMBED_BATCH_SIZE = 256


def embed_text_chunks(conn) -> None:
    """Fill text_chunks.embedding for every row that has no vector yet.

    A catalog reload and every O*NET reload insert chunks without vectors, so
    this step re-embeds exactly what was replaced. An unchanged catalog keeps
    its course vectors. On a boot where those rows already have vectors, the
    query returns at once for them.
    Each batch commits on its own, so an interrupted run resumes where it
    stopped instead of starting over.
    """
    pending = conn.execute(
        "SELECT id, chunk_text FROM text_chunks WHERE embedding IS NULL ORDER BY id"
    ).fetchall()
    if not pending:
        print("text_chunks: all rows already embedded")
        return

    # Imported here, not at module top, so the loader still runs (and the
    # API still starts) on a machine without the model installed.
    from ai.nlp.embeddings.sentence_transformer import MODEL_NAME, encode, to_pgvector

    print(f"embedding {len(pending)} text_chunks with {MODEL_NAME} ...")
    done = 0
    for start in range(0, len(pending), EMBED_BATCH_SIZE):
        batch = pending[start : start + EMBED_BATCH_SIZE]
        vectors = encode([text for _, text in batch])
        with conn.transaction():
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE text_chunks SET embedding = %s::vector WHERE id = %s",
                    [(to_pgvector(vec), row_id) for (row_id, _), vec in zip(batch, vectors)],
                )
        done += len(batch)
        print(f"  embedded {done}/{len(pending)}")
    print(f"embedded {done} text_chunks")


def print_counts(conn) -> None:
    tables = (
        "courses",
        "course_links",
        "programs",
        "program_courses",
        "occupations",
        "occupation_skills",
        "occupation_knowledge",
        "occupation_education",
        "occupation_technologies",
        "skill_terms",
        "text_chunks",
        "syllabus_triples",
    )
    for table in tables:
        count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"{table}: {count}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"ingest command failed: {exc.cmd}", file=sys.stderr)
        raise SystemExit(exc.returncode or 1) from exc
