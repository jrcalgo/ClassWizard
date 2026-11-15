"""Rank the courses a student still needs against the careers they chose.

Implements the "/recommend" plan in the semantic-search spec. No language
model is involved: candidates come from the parsed DegreeWorks audit, and
each candidate is scored by cosine similarity between its catalog
description vector and each chosen occupation's vector (text_chunks).

Decisions taken (Nov 6, defaults from the spec):
  * Several careers combine by MAX: a course that strongly serves one chosen
    career is not pulled down by the others.
  * Prerequisites are a FLAG, never a filter: course_links flattens "A or B"
    rules, so it cannot decide eligibility on its own.
  * Elective pools ("3 Credits in ITSC 4@") are not expanded yet: the parser
    returns no codes for them. Planned as a separate parser change.
  * Each audit is ranked against the catalog for its level: undergraduate
    audits against "Undergraduate 2026-2027", graduate audits against
    "Graduate 2026-2027". A level whose catalog zip was not supplied raises
    UnsupportedAudit with a message saying which catalog is missing.

Student data: only course codes, requirement blocks and the audit's level
are read. Nothing from the audit is logged or returned beyond course codes.

The functions take a psycopg connection and plain dicts, so they can be
tested without HTTP or Redis. backend/main.py wires them to POST /recommend.
"""

from __future__ import annotations

from ai.nlp.embeddings.sentence_transformer import MODEL_NAME

CATALOG_YEAR = "2026-2027"
CATALOG = f"Undergraduate {CATALOG_YEAR}"  # default for callers with no audit


class UnsupportedAudit(ValueError):
    """The audit's level is unknown, or its catalog is not loaded."""


class MissingVectors(RuntimeError):
    """Occupation or course vectors are missing: the embedding step has not run."""


def audit_level(audit: dict) -> str | None:
    """'Undergraduate' or 'Graduate' from the audit's Level field, else None.

    "undergrad" is checked first because "Undergraduate" also contains "grad".
    """
    level = (audit.get("level") or "").lower()
    if "undergrad" in level:
        return "Undergraduate"
    if any(word in level for word in ("grad", "master", "doctor")):
        return "Graduate"
    return None


def catalog_for(audit: dict) -> str | None:
    """Catalog name for the audit's level, e.g. 'Graduate 2026-2027'."""
    level = audit_level(audit)
    return f"{level} {CATALOG_YEAR}" if level else None


def is_supported(audit: dict) -> bool:
    """True when the audit's level maps to a catalog (whether or not it is loaded)."""
    return catalog_for(audit) is not None


def catalog_loaded(conn, catalog: str) -> bool:
    row = conn.execute("SELECT 1 FROM courses WHERE catalog_name = %s LIMIT 1", (catalog,)).fetchone()
    return row is not None


def taken_codes(audit: dict) -> set[str]:
    """Courses the student has completed, is taking, or is registered for."""
    keys = ("courses_completed", "courses_in_progress", "courses_preregistered")
    return {course["code"] for key in keys for course in audit.get(key) or []}


def satisfied_codes(audit: dict) -> set[str]:
    """Courses that count toward prerequisites: completed or in progress.

    Preregistered courses are not counted: they have not been started.
    """
    keys = ("courses_completed", "courses_in_progress")
    return {course["code"] for key in keys for course in audit.get(key) or []}


def candidate_courses(audit: dict) -> dict[str, list[str]]:
    """Still-needed course codes, minus taken ones, mapped to their requirement blocks.

    A course named in several "Still needed" blocks keeps all of them.
    """
    taken = taken_codes(audit)
    blocks: dict[str, list[str]] = {}
    for requirement in audit.get("courses_not_taken") or []:
        block = requirement.get("block") or ""
        for code in requirement.get("course_codes") or []:
            if code in taken:
                continue
            names = blocks.setdefault(code, [])
            if block not in names:
                names.append(block)
    return blocks


def _credits(credit_min, credit_max, credit_raw):
    if credit_min is not None and credit_min == credit_max:
        return credit_min
    return credit_raw


def recommend(conn, audit: dict, soc_codes: list[str], limit: int = 10, catalog: str | None = None) -> dict:
    """Return still-needed courses ranked by best match to the chosen careers."""
    catalog = catalog or catalog_for(audit)
    if catalog is None:
        raise UnsupportedAudit(f"audit level {audit.get('level')!r} is not recognised")
    if not catalog_loaded(conn, catalog):
        raise UnsupportedAudit(f"the {catalog} catalog is not loaded yet")

    occupations = conn.execute(
        "SELECT soc_code, title FROM occupations WHERE soc_code = ANY(%s)",
        (soc_codes,),
    ).fetchall()
    titles = dict(occupations)
    missing = [soc for soc in soc_codes if soc not in titles]
    if missing:
        raise MissingVectors(f"occupations not loaded: {', '.join(missing)}")
    embedded = {
        row[0]
        for row in conn.execute(
            """
            SELECT source_key FROM text_chunks
            WHERE source_type = 'occupation' AND source_key = ANY(%s) AND embedding IS NOT NULL
            """,
            (soc_codes,),
        ).fetchall()
    }
    missing = [soc for soc in soc_codes if soc not in embedded]
    if missing:
        raise MissingVectors(f"occupation vectors missing: {', '.join(missing)}")

    candidates = candidate_courses(audit)
    codes = sorted(candidates)
    rows = conn.execute(
        """
        SELECT code, title, credit_min, credit_max, credit_raw
        FROM courses WHERE catalog_name = %s AND code = ANY(%s)
        """,
        (catalog, codes),
    ).fetchall()
    courses = {code: (title, _credits(cmin, cmax, raw)) for code, title, cmin, cmax, raw in rows}
    unmatched = [
        {"code": code, "requirement_blocks": candidates[code]}
        for code in codes
        if code not in courses
    ]
    matched = sorted(courses)

    result = {
        "catalog": catalog,
        "model": MODEL_NAME,
        "occupations": [{"soc_code": soc, "title": titles[soc]} for soc in soc_codes],
        "recommendations": [],
        "unmatched": unmatched,
        "candidate_count": len(codes),
    }
    if not matched:
        return result

    # Exact cosine similarity for every (course, occupation) pair. The set is
    # small (tens of courses x at most 5 careers), so no index is involved.
    pairs = conn.execute(
        """
        SELECT c.source_key, o.source_key, 1 - (c.embedding <=> o.embedding)
        FROM text_chunks c
        JOIN text_chunks o
          ON o.source_type = 'occupation' AND o.source_key = ANY(%s)
        WHERE c.source_type = 'course' AND c.source_key = ANY(%s)
          AND c.metadata->>'catalog' = %s
          AND c.embedding IS NOT NULL AND o.embedding IS NOT NULL
        """,
        (soc_codes, matched, catalog),
    ).fetchall()
    similarity: dict[str, dict[str, float]] = {}
    for course, soc, value in pairs:
        similarity.setdefault(course, {})[soc] = round(float(value), 4)
    missing = [code for code in matched if code not in similarity]
    if missing:
        raise MissingVectors(f"course vectors missing: {', '.join(missing)}")

    prerequisites: dict[str, list[str]] = {}
    for course, target in conn.execute(
        """
        SELECT course_code, target_code FROM course_links
        WHERE catalog_name = %s AND kind = 'prerequisite' AND course_code = ANY(%s)
        ORDER BY course_code, target_code
        """,
        (catalog, matched),
    ).fetchall():
        targets = prerequisites.setdefault(course, [])
        if target not in targets:
            targets.append(target)
    satisfied = satisfied_codes(audit)

    ranked = []
    for code in matched:
        by_occupation = similarity[code]
        title, credit_hours = courses[code]
        ranked.append(
            {
                "code": code,
                "title": title,
                "credits": credit_hours,
                "requirement_blocks": candidates[code],
                "score": max(by_occupation.values()),
                "similarity_by_occupation": by_occupation,
                "prerequisites": [
                    {"code": target, "met": target in satisfied}
                    for target in prerequisites.get(code, [])
                ],
            }
        )
    # Highest score first; ties broken by course code so the order is stable.
    ranked.sort(key=lambda item: (-item["score"], item["code"]))
    result["recommendations"] = ranked[:limit]
    return result
