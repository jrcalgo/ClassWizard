"""List keyword-matched candidate courses for each golden-set item (read-only).

Helps a person fill must_include in data/eval/golden_queries.json. It uses
plain keyword matching on course titles and descriptions, never the
embeddings, so the golden set is not built from the system it will judge.

It also checks the draft itself: SOC codes and titles against the
occupations table, and every must_include code against the catalog.

Run from the repo root (PowerShell). The file is piped in, so editing it
needs no image rebuild:
    Get-Content -Raw data\\eval\\golden_queries.json |
        docker compose exec -T backend python3 -m backend.storage.database.golden_candidates
"""

from __future__ import annotations

import json
import os
import sys

MAX_CANDIDATES = 25


def main() -> int:
    import psycopg

    golden = json.load(sys.stdin)
    catalog = golden.get("catalog", "Undergraduate 2026-2027")
    problems = []

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for item in golden["items"]:
            label = item.get("query") or f"{item.get('soc_code')} {item.get('occupation_title', '')}"
            print(f"\n{item['id']} [{item['kind']}] {label}  (status: {item.get('status')})")

            # 1. Occupation items: the SOC code exists and the title matches.
            if item["kind"] == "occupation":
                row = conn.execute(
                    "SELECT title FROM occupations WHERE soc_code = %s", (item["soc_code"],)
                ).fetchone()
                if row is None:
                    problems.append(f"{item['id']}: SOC code {item['soc_code']} not in occupations")
                elif row[0] != item.get("occupation_title"):
                    print(f"  note: O*NET title is {row[0]!r}")

            # 2. Every must_include code exists in the catalog.
            for code in item.get("must_include", []):
                found = conn.execute(
                    "SELECT title FROM courses WHERE catalog_name = %s AND code = %s",
                    (catalog, code),
                ).fetchone()
                if found is None:
                    problems.append(f"{item['id']}: must_include {code} not in catalog {catalog!r}")
                else:
                    print(f"  must_include {code}: {found[0]}")

            # 3. Keyword candidates: title matches first, then description matches.
            keywords = item.get("topic_keywords") or []
            if not keywords:
                continue
            patterns = [f"%{word}%" for word in keywords]
            # Rank by how many different keywords a course matches (title or
            # description), then title matches first, so the most on-topic
            # courses are not cut off by alphabetical order.
            rows = conn.execute(
                """
                SELECT c.code, c.title, (c.title ILIKE ANY(%s)) AS in_title,
                       (SELECT count(*) FROM unnest(%s::text[]) AS p(pattern)
                        WHERE c.title ILIKE p.pattern OR c.description ILIKE p.pattern) AS hits
                FROM courses c
                WHERE c.catalog_name = %s
                  AND (c.title ILIKE ANY(%s) OR c.description ILIKE ANY(%s))
                ORDER BY hits DESC, in_title DESC, c.code
                LIMIT %s
                """,
                (patterns, patterns, catalog, patterns, patterns, MAX_CANDIDATES),
            ).fetchall()
            chosen = set(item.get("must_include", []))
            for code, title, in_title, hits in rows:
                mark = "*" if code in chosen else " "
                where = "title" if in_title else "desc "
                print(f"  {mark} {code:<10} [{where}] {hits} kw  {title}")
            if not rows:
                print("  (no keyword matches: try other keywords)")

    if problems:
        print("\nPROBLEMS:\n  " + "\n  ".join(problems))
        return 1
    print("\nno problems found in the draft")
    return 0


if __name__ == "__main__":
    sys.exit(main())
