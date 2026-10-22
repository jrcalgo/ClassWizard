"""Stage 6b: course-to-course links (layer C), stored as edge lists.

Three kinds of link, each kept as one edge per (source, target) pair so they map straight
onto link tables later:

* ``crosslist``   - from the Cross-listed Course(s) field. Never merged transitively:
                    joining cross-lists into groups produced a false 21-course group.
* ``exclusion``   - "no credit if ..." rules, which exist only in descriptions and
                    restrictions; found by sentence templates, kept with the evidence text.
* ``requisite``   - every course a requisite field mentions, with whether it sits in the
                    logic tree or only in advisory text.

A target that is not a course in this catalog (a graduate number, a retired code) is kept,
with ``target_resolved: false``, so a later catalog can resolve it.
"""
from __future__ import annotations

import re

from .requisites import mentioned_codes

# Sentences that deny credit when another course has been (or will be) taken.
EXCLUSION_RES = [re.compile(p, re.IGNORECASE) for p in (
    r"may not be taken for credit[^.]*?\bif\b[^.]*?credit",
    r"credit (?:will|may|can)(?: not|not) be (?:given|granted|earned|received|awarded) for",
    r"(?:will|may) not receive credit for",
    r"may not take [^.]*? for credit",
    r"(?:receive|earn) credit for either [^.]*?but not both",
    r"credit (?:is|will be) not (?:given|granted)",
)]
SENTENCE_RE = re.compile(r"[^.]*?(?:\.(?=\s|$)|$)")
REVIEW_HINT = re.compile(r"or higher|or above|any\b|-level|level course", re.IGNORECASE)


def sentences(text: str) -> list[str]:
    """Split text into sentences without splitting course codes or decimals."""
    return [s.strip() for s in SENTENCE_RE.findall(text) if s.strip()]


def exclusion_edges(code: str, texts: list[tuple[str, str]]) -> list[dict]:
    """Exclusion edges for one course from (field name, text) pairs."""
    edges: list[dict] = []
    for field_name, text in texts:
        for sentence in sentences(text):
            if not any(r.search(sentence) for r in EXCLUSION_RES):
                continue
            others = [c for c in mentioned_codes(sentence) if c != code]
            if not others:
                continue
            for other in others:
                edges.append({
                    "type": "exclusion", "source": code, "target": other,
                    "field": field_name, "evidence": sentence,
                    # 'credit for MATH 1120 or higher' blocks a range, not one course
                    "needs_review": bool(REVIEW_HINT.search(sentence)),
                })
    return edges


def crosslist_edges(code: str, normalized: dict) -> list[dict]:
    """One edge per course named in the cross-list field."""
    return [{"type": "crosslist", "source": code, "target": ref["code"],
             "section": ref["section"]} for ref in normalized["courses"] if ref["code"] != code]


def requisite_edges(code: str, field_name: str, parsed: dict) -> list[dict]:
    """One edge per course mentioned in a requisite field."""
    in_tree = set(tree_codes(parsed["tree"])) if parsed["tree"] else set()
    advisory = {c for a in parsed["advisory"] for c in a["courses"]}
    return [{"type": "requisite", "source": code, "target": target, "field": field_name,
             "timing": parsed["timing"], "in_tree": target in in_tree,
             "advisory_only": target in advisory and target not in in_tree,
             "status": parsed["status"]}
            for target in parsed["courses_mentioned"] if target != code]


def tree_codes(node: dict) -> list[str]:
    """All course codes at the leaves of a requisite tree."""
    if node.get("type") == "course":
        return [node["code"]]
    return [c for child in node.get("items", []) for c in tree_codes(child)]


def finish_edges(edges: list[dict], known_codes: set[str]) -> list[dict]:
    """Add resolution and reciprocity flags, then sort for stable output.

    ``reciprocal`` is True when the same kind of link is also printed on the target course
    (a cross-list or corequisite listed on both sides).
    """
    keyset = {(e["type"], e.get("field"), e["source"], e["target"]) for e in edges}
    for edge in edges:
        edge["target_resolved"] = edge["target"] in known_codes
        field_name = edge.get("field")
        if edge["type"] == "exclusion":
            # an exclusion printed on the other course may sit in either text field
            edge["reciprocal"] = any((edge["type"], f, edge["target"], edge["source"]) in keyset
                                     for f in ("description", "Restriction(s)"))
        else:
            edge["reciprocal"] = (edge["type"], field_name, edge["target"], edge["source"]) in keyset
    return sorted(edges, key=lambda e: (e["type"], e["source"], e.get("field") or "", e["target"]))
