"""Gather cited evidence for one student question (the "R" in RAG).

Implements the retrieval steps of the "/explain" plan in the semantic-search
spec. Evidence comes from two kinds of lookups:

  by key (exact):  course facts, the requirement blocks a course satisfies,
                   catalog-listed prerequisites, /recommend match scores,
                   career descriptions, top O*NET skills and technologies
  by meaning:      the question is embedded with the shared encoder and
                   compared with the recommended courses (to pick which ones
                   the question is about), with syllabus summaries and
                   learning objectives, and with the whole catalog (for
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
MIN_FOCUS_SIMILARITY = 0.35  # a recommended course less related than this is left out
OPEN_SEARCH = 2         # extra catalog courses found by searching the question
MIN_OPEN_SIMILARITY = 0.30  # below this an open-search hit is noise, not evidence
SYLLABUS_SEARCH = 3     # courses found through their syllabus text and objectives
MIN_SYLLABUS_SIMILARITY = 0.35
OBJECTIVES_PER_COURSE = 3
MAX_TEXT = 600          # characters kept from a long description
MAX_BLOCK_COURSES = 6   # options listed for a requirement block named in the question
# Words that never identify a requirement block on their own.
_BLOCK_STOPWORDS = {"and", "the", "for", "with", "of", "in", "or", "to", "a", "an"}

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


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", text.lower()) if w not in _BLOCK_STOPWORDS]


def named_blocks(question: str, audit: dict) -> list[tuple[str, list[str]]]:
    """Still-needed requirement blocks the question names, with their untaken courses.

    A block matches when every word of its name appears in the question, where
    words match on their first four letters ("math elective" names the
    "Mathematics Elective" block, "natural sciences" names "Natural Science").
    Similarity search alone misses these: "Ethics requirement" is closer to
    ethics courses in other departments than to ITSC 3688, the only course that
    satisfies the student's Ethics block.
    """
    asked = {w[:4] for w in _words(question)}
    taken = taken_codes(audit)
    found: list[tuple[str, list[str]]] = []
    for requirement in audit.get("courses_not_taken") or []:
        block = (requirement.get("block") or "").strip()
        words = _words(block)
        codes = [c for c in requirement.get("course_codes") or [] if c not in taken]
        if words and codes and all(w[:4] in asked for w in words):
            found.append((block, codes))
    return found


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


def _ranked_by_question(conn, vector: str, codes: list[str], catalog: str) -> list[tuple[str, float]]:
    """Course codes (restricted to `codes`) ordered by similarity to the question."""
    if not codes:
        return []
    return conn.execute(
        """
        SELECT source_key, 1 - (embedding <=> %s::vector) AS similarity
        FROM text_chunks
        WHERE source_type = 'course' AND source_key = ANY(%s) AND embedding IS NOT NULL
          AND metadata->>'catalog' = %s
        ORDER BY similarity DESC, source_key
        """,
        (vector, codes, catalog),
    ).fetchall()


def _syllabus_search(conn, vector: str, level: str, exclude: set[str], limit: int) -> list[tuple[str, float]]:
    """Courses whose syllabus summary or objectives are closest to the question."""
    rows = conn.execute(
        """
        SELECT metadata->>'code', max(1 - (embedding <=> %s::vector)) AS similarity
        FROM text_chunks
        WHERE source_type IN ('syllabus_course', 'syllabus_objective') AND embedding IS NOT NULL
          AND metadata->>'level' = %s
          -- Course numbers decide the level when a record's own label is wrong
          -- (some 5000-level syllabi are labelled undergraduate).
          AND (substring(metadata->>'code' from '[0-9]{4}')::int >= 5000) = (%s = 'graduate')
        GROUP BY 1
        ORDER BY similarity DESC
        LIMIT %s
        """,
        (vector, level, level, limit + len(exclude) + 10),
    ).fetchall()
    hits = [(code, sim) for code, sim in rows if code not in exclude and sim >= MIN_SYLLABUS_SIMILARITY]
    return hits[:limit]


def _syllabus_rows(conn, codes: list[str]) -> dict[str, tuple]:
    if not codes:
        return {}
    rows = conn.execute(
        "SELECT course_code, title, description FROM syllabus_courses WHERE course_code = ANY(%s)",
        (codes,),
    ).fetchall()
    return {row[0]: row[1:] for row in rows}


def _objectives(conn, vector: str, codes: list[str]) -> dict[str, list[str]]:
    """Each course's syllabus objectives, closest to the question first."""
    found: dict[str, list[str]] = {}
    if not codes:
        return found
    for code, text in conn.execute(
        """
        SELECT o.course_code, o.text
        FROM syllabus_objectives o
        JOIN text_chunks t ON t.source_type = 'syllabus_objective'
         AND t.source_key = o.course_code || '#' || o.objective_id
        WHERE o.course_code = ANY(%s) AND t.embedding IS NOT NULL
        ORDER BY o.course_code, t.embedding <=> %s::vector
        """,
        (codes, vector),
    ).fetchall():
        found.setdefault(code, [])
        if len(found[code]) < OBJECTIVES_PER_COURSE:
            found[code].append(_clip(text))
    return found


def _with_objectives(item: dict, objectives: list[str]) -> dict:
    if objectives:
        item["text"] += " Syllabus learning objectives: " + "; ".join(objectives) + "."
    return item


def _open_search(conn, vector: str, exclude: set[str], limit: int, catalog: str) -> list[tuple[str, float]]:
    """Search the student's catalog, over-fetching so excluded courses don't empty the list (D4)."""
    rows = conn.execute(
        """
        SELECT source_key, 1 - (embedding <=> %s::vector) AS similarity
        FROM text_chunks
        WHERE source_type = 'course' AND embedding IS NOT NULL
          AND metadata->>'catalog' = %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (vector, catalog, vector, limit + len(exclude) + 20),
    ).fetchall()
    hits = [(code, sim) for code, sim in rows if code not in exclude and sim >= MIN_OPEN_SIMILARITY]
    return hits[:limit]


def retrieve_evidence(
    conn,
    question: str,
    audit: dict,
    recommendation: dict,
    soc_codes: list[str],
    catalog: str | None = None,
) -> list[dict]:
    """Evidence items for one question, most important first, at most MAX_ITEMS.

    The catalog defaults to the one /recommend ranked against (the audit's level).
    """
    catalog = catalog or recommendation.get("catalog") or CATALOG
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
    # 1b. Requirement blocks named in the question ("Ethics requirement"), by key:
    #     every untaken option of the block, so an answer can list all of them.
    by_block: dict[str, list[str]] = {}
    for block, codes in named_blocks(question, audit):
        for code in codes:
            if code not in named and len(by_block) < MAX_BLOCK_COURSES:
                by_block.setdefault(code, []).append(block)
    # 2. Recommended courses that are actually related to the question.
    focus = [
        code for code, sim in _ranked_by_question(conn, vector, list(recommended), catalog)
        if code not in named and code not in by_block and sim >= MIN_FOCUS_SIMILARITY
    ][:FOCUS_COURSES]
    # 3. Courses matching the question through their syllabus, then the catalog,
    #    never already-taken ones.
    exclude = set(named) | set(by_block) | set(focus) | taken_codes(audit)
    level = "graduate" if catalog.startswith("Graduate") else "undergraduate"
    by_syllabus = _syllabus_search(conn, vector, level, exclude, SYLLABUS_SEARCH)
    found = _open_search(conn, vector, exclude | {code for code, _ in by_syllabus}, OPEN_SEARCH, catalog)
    matched = [code for code, _ in by_syllabus] + [code for code, _ in found]

    wanted = named + list(by_block) + matched + focus
    rows = _course_rows(conn, wanted, catalog)
    prereqs = _prerequisites(conn, wanted, catalog)
    syllabi = _syllabus_rows(conn, wanted)
    objectives = _objectives(conn, vector, wanted)

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
        items.append(_with_objectives(
            _course_item(
                code, rows[code], audit, blocks_by_code.get(code, []), prereqs.get(code, []),
                rec.get("similarity_by_occupation", {}), titles, None,
            ),
            objectives.get(code, []),
        ))
    for code, blocks in by_block.items():
        if code not in rows:
            continue
        rec = recommended.get(code, {})
        items.append(_with_objectives(
            _course_item(
                code, rows[code], audit, blocks_by_code.get(code, blocks), prereqs.get(code, []),
                rec.get("similarity_by_occupation", {}), titles,
                "One of the options for the student's still-needed " + " and ".join(blocks) + " requirement.",
            ),
            objectives.get(code, []),
        ))
    for code in matched:
        origin = "Matches the question" + (
            "; part of the student's remaining requirements." if code in blocks_by_code
            else "; not part of the student's listed remaining requirements."
        )
        if code in rows:
            item = _course_item(
                code, rows[code], audit, blocks_by_code.get(code, []), prereqs.get(code, []),
                recommended.get(code, {}).get("similarity_by_occupation", {}), titles, origin,
            )
        elif code in syllabi:
            title, description = syllabi[code]
            item = {"id": code, "kind": "course",
                    "text": f"{code} {title or ''}. {_clip(description)} {origin}".replace(" . ", ". ")}
        else:
            continue
        items.append(_with_objectives(item, objectives.get(code, [])))
    for code in focus:
        rec = recommended[code]
        items.append(_with_objectives(
            _course_item(
                code, rows[code], audit, rec.get("requirement_blocks", []), prereqs.get(code, []),
                rec.get("similarity_by_occupation", {}), titles,
                f"Recommended for the student's chosen careers (rank {list(recommended).index(code) + 1}).",
            ),
            objectives.get(code, []),
        ))
    items.extend(_career_items(conn, soc_codes))
    return items[:MAX_ITEMS]
