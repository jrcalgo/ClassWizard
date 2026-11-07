"""Gather cited evidence for one student question (the "R" in RAG).

Implements the retrieval steps of the "/explain" plan in the semantic-search
spec. Evidence comes from two kinds of lookups:

  by key (exact):  course facts, the requirement blocks a course satisfies,
                   catalog-listed prerequisites, /recommend match scores,
                   career descriptions, top O*NET skills and technologies
  by meaning:      the question is embedded with the shared encoder and
                   compared with the recommended courses (to pick which ones
                   the question is about) and with the whole catalog (for
                   open questions such as "is there an elective on ML?")

Every item is {"id", "kind", "text"}. The id is what the answer must cite:
a course code ("ITSC 3160"), a SOC code ("15-1242.00") or "catalog:<code>"
for a course that is not in the catalog.

Student data: only course codes and their status (taken / still needed) are
used. Names, IDs and advisors are not in the audit any more, and nothing
else from the audit enters an evidence item.
"""

from __future__ import annotations

import re

from ai.nlp.embeddings.sentence_transformer import encode, to_pgvector
from ai.recommendations.ranking import CATALOG, candidate_courses, satisfied_codes, taken_codes

MAX_ITEMS = 10          # cap on evidence items per answer (prompt budget)
FOCUS_COURSES = 3       # recommended courses kept, chosen by closeness to the question
OPEN_SEARCH = 2         # extra catalog courses found by searching the question
MIN_OPEN_SIMILARITY = 0.30  # below this an open-search hit is noise, not evidence
MAX_TEXT = 600          # characters kept from a long description

# Course codes as students type them: "ITSC 3160", "itsc3160", "ECGR 2112L".
_CODE = re.compile(r"\b([A-Za-z]{2,5})\s?(\d{4}[A-Za-z]?)\b")


def mentioned_codes(question: str) -> list[str]:
    """Code-shaped words in the question, normalised to catalog form.

    Deliberately loose ("itsc3160" counts), so it also catches ordinary words
    before a year ("just 2026"). retrieve_evidence() keeps only codes whose
    subject exists in the catalog.
    """
    seen: list[str] = []
    for subject, number in _CODE.findall(question):
        code = f"{subject.upper()} {number.upper()}"
        if code not in seen:
            seen.append(code)
    return seen


def _clip(text: str | None) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 3].rstrip() + "..."


def _status(code: str, audit: dict) -> str | None:
    for key, label in (
        ("courses_completed", "completed"),
        ("courses_in_progress", "in progress"),
        ("courses_preregistered", "registered for a future term"),
    ):
        if any(course.get("code") == code for course in audit.get(key) or []):
            return label
    return None


def _course_rows(conn, codes: list[str], catalog: str) -> dict[str, tuple]:
    if not codes:
        return {}
    rows = conn.execute(
        """
        SELECT code, title, description, credit_min, credit_max, credit_raw
        FROM courses WHERE catalog_name = %s AND code = ANY(%s)
        """,
        (catalog, codes),
    ).fetchall()
    return {row[0]: row[1:] for row in rows}


def _prerequisites(conn, codes: list[str], catalog: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    if not codes:
        return found
    for course, target in conn.execute(
        """
        SELECT course_code, target_code FROM course_links
        WHERE catalog_name = %s AND kind = 'prerequisite' AND course_code = ANY(%s)
        ORDER BY course_code, target_code
        """,
        (catalog, codes),
    ).fetchall():
        targets = found.setdefault(course, [])
        if target not in targets:
            targets.append(target)
    return found


def _course_item(code, row, audit, blocks, prereqs, matches, titles, origin) -> dict:
    """One evidence item with everything known about a course, cited by its code."""
    title, description, credit_min, credit_max, credit_raw = row
    hours = credit_min if credit_min is not None and credit_min == credit_max else credit_raw
    parts = [f"{code} {title} ({hours} credits). {_clip(description)}"]
    status = _status(code, audit)
    if status:
        parts.append(f"The student has this course {status}.")
    if blocks:
        parts.append("Satisfies the student's still-needed requirement block(s): " + ", ".join(blocks) + ".")
    if prereqs:
        satisfied = satisfied_codes(audit)
        listed = ", ".join(
            f"{p} ({'completed or in progress' if p in satisfied else 'not completed'})" for p in prereqs
        )
        parts.append(
            f"Catalog-listed prerequisites: {listed}. Alternatives in 'A or B' rules are "
            "listed separately, so one unmet entry may already be covered by another."
        )
    if matches:
        listed = ", ".join(f"{titles.get(soc, soc)} {value:.2f}" for soc, value in matches.items())
        parts.append(f"Career match by description similarity (higher is closer): {listed}.")
    if origin:
        parts.append(origin)
    return {"id": code, "kind": "course", "text": " ".join(parts)}


def _career_items(conn, soc_codes: list[str]) -> list[dict]:
    items = []
    for soc in soc_codes:
        row = conn.execute(
            "SELECT title, description FROM occupations WHERE soc_code = %s", (soc,)
        ).fetchone()
        if row is None:
            continue
        title, description = row
        top = conn.execute(
            """
            SELECT element_name FROM (
                SELECT element_name, score FROM occupation_skills
                WHERE soc_code = %s AND scale_id = 'IM'
                UNION ALL
                SELECT element_name, score FROM occupation_knowledge
                WHERE soc_code = %s AND scale_id = 'IM'
            ) AS rated
            ORDER BY score DESC, element_name
            LIMIT 5
            """,
            (soc, soc),
        ).fetchall()
        tech = conn.execute(
            """
            SELECT DISTINCT name FROM occupation_technologies
            WHERE soc_code = %s AND hot_technology
            ORDER BY name LIMIT 8
            """,
            (soc,),
        ).fetchall()
        text = f"{title}: {_clip(description)}"
        if top:
            text += " Most important skills and knowledge (O*NET importance): " + ", ".join(r[0] for r in top) + "."
        if tech:
            text += " In-demand technologies: " + ", ".join(r[0] for r in tech) + "."
        items.append({"id": soc, "kind": "career", "text": text})
    return items


def _ranked_by_question(conn, vector: str, codes: list[str]) -> list[tuple[str, float]]:
    """Course codes (restricted to `codes`) ordered by similarity to the question."""
    if not codes:
        return []
    return conn.execute(
        """
        SELECT source_key, 1 - (embedding <=> %s::vector) AS similarity
        FROM text_chunks
        WHERE source_type = 'course' AND source_key = ANY(%s) AND embedding IS NOT NULL
        ORDER BY similarity DESC, source_key
        """,
        (vector, codes),
    ).fetchall()


def _open_search(conn, vector: str, exclude: set[str], limit: int) -> list[tuple[str, float]]:
    """Whole-catalog search, over-fetching so excluded courses don't empty the list (D4)."""
    rows = conn.execute(
        """
        SELECT source_key, 1 - (embedding <=> %s::vector) AS similarity
        FROM text_chunks
        WHERE source_type = 'course' AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (vector, vector, limit + len(exclude) + 20),
    ).fetchall()
    hits = [(code, sim) for code, sim in rows if code not in exclude and sim >= MIN_OPEN_SIMILARITY]
    return hits[:limit]


def retrieve_evidence(
    conn,
    question: str,
    audit: dict,
    recommendation: dict,
    soc_codes: list[str],
    catalog: str = CATALOG,
) -> list[dict]:
    """Evidence items for one question, most important first, at most MAX_ITEMS."""
    titles = {o["soc_code"]: o["title"] for o in recommendation.get("occupations", [])}
    recommended = {r["code"]: r for r in recommendation.get("recommendations", [])}
    blocks_by_code = candidate_courses(audit)
    vector = to_pgvector(encode([question])[0])

    # 1. Courses named in the question, fetched by key. A code counts only if
    #    its subject is a real catalog subject, so "just 2026" is ignored
    #    while a typo like "ITSC 9999" still gets a "not in the catalog" note.
    named = mentioned_codes(question)
    if named:
        subjects = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT subject FROM courses WHERE catalog_name = %s AND subject = ANY(%s)",
                (catalog, [code.split()[0] for code in named]),
            ).fetchall()
        }
        named = [code for code in named if code.split()[0] in subjects]
    # 2. Recommended courses closest to the question.
    focus = [code for code, _ in _ranked_by_question(conn, vector, list(recommended))]
    focus = [code for code in focus if code not in named][:FOCUS_COURSES]
    # 3. Catalog courses matching an open question, never already-taken ones.
    exclude = set(named) | set(focus) | taken_codes(audit)
    found = _open_search(conn, vector, exclude, OPEN_SEARCH)

    wanted = named + focus + [code for code, _ in found]
    rows = _course_rows(conn, wanted, catalog)
    prereqs = _prerequisites(conn, wanted, catalog)

    items: list[dict] = []
    for code in named:
        if code not in rows:
            items.append(
                {
                    "id": f"catalog:{code}",
                    "kind": "note",
                    "text": f"{code} is not in the {catalog} catalog.",
                }
            )
            continue
        rec = recommended.get(code, {})
        items.append(
            _course_item(
                code, rows[code], audit, blocks_by_code.get(code, []), prereqs.get(code, []),
                rec.get("similarity_by_occupation", {}), titles, None,
            )
        )
    for code in focus:
        rec = recommended[code]
        items.append(
            _course_item(
                code, rows[code], audit, rec.get("requirement_blocks", []), prereqs.get(code, []),
                rec.get("similarity_by_occupation", {}), titles,
                f"Recommended for the student's chosen careers (rank {list(recommended).index(code) + 1}).",
            )
        )
    items.extend(_career_items(conn, soc_codes))
    for code, _ in found:
        if code in rows:
            items.append(
                _course_item(
                    code, rows[code], audit, blocks_by_code.get(code, []), prereqs.get(code, []),
                    {}, titles,
                    "Found by searching the catalog for the question; not part of the "
                    "student's listed remaining requirements.",
                )
            )
    return items[:MAX_ITEMS]
