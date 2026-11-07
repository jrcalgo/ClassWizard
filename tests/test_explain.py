"""Unit tests for the database-free parts of /explain (no model, no database).

Run from the repo root:
    python -m pytest tests/test_explain.py
"""

import pytest

from ai.nlp.explanations.rag import (
    NOT_FOUND,
    build_messages,
    check_citations,
    cited_ids,
    generate,
    strip_thinking,
    student_context,
)
from ai.nlp.explanations.retrieval import mentioned_codes

EVIDENCE = [
    {"id": "ITSC 3160", "kind": "course", "text": "ITSC 3160 Database Design and Implementation."},
    {"id": "15-1242.00", "kind": "career", "text": "Database Administrators: ..."},
]


def test_mentioned_codes_normalises_what_students_type():
    assert mentioned_codes("Why itsc3160 and ITSC 3155? Also ECGR 2112L") == [
        "ITSC 3160",
        "ITSC 3155",
        "ECGR 2112L",
    ]
    assert mentioned_codes("no codes here at all") == []
    # Loose on purpose: retrieval drops it because JUST is not a catalog subject.
    assert mentioned_codes("just 2026") == ["JUST 2026"]


def test_cited_ids_splits_grouped_citations_and_keeps_order():
    answer = "It covers SQL [ITSC 3160]. Admins need it [15-1242.00; ITSC 3160]."
    assert cited_ids(answer) == ["ITSC 3160", "15-1242.00"]


def test_check_citations_flags_ids_that_were_not_retrieved():
    good = check_citations("Covers SQL [ITSC 3160].", EVIDENCE)
    assert good == {"citations": ["ITSC 3160"], "unknown_citations": [], "grounded": True}
    bad = check_citations("Take ITSC 4155 [ITSC 4155].", EVIDENCE)
    assert bad["unknown_citations"] == ["ITSC 4155"] and not bad["grounded"]


def test_uncited_answer_is_not_grounded_but_not_found_is():
    assert not check_citations("ITSC 3160 is great.", EVIDENCE)["grounded"]
    assert check_citations(f"That is {NOT_FOUND}.", EVIDENCE)["grounded"]


def test_strip_thinking_removes_reasoning_block():
    assert strip_thinking("<think>\nweighing it\n</think>\n\nAnswer [ITSC 3160].") == "Answer [ITSC 3160]."


def test_student_context_is_a_whitelist():
    audit = {
        "major": "Computer Science",
        "catalog_year": "2025-2026",
        "student_name": "Should Never Appear",
        "advisors": ["Nor This"],
        "courses_completed": [{"code": "ITSC 2214"}],
    }
    assert student_context(audit) == {"major": "Computer Science", "catalog_year": "2025-2026"}


def test_prompt_holds_evidence_ids_and_no_student_identifiers():
    audit = {"major": "Computer Science", "student_name": "Should Never Appear"}
    messages = build_messages("Why ITSC 3160?", EVIDENCE, student_context(audit))
    user = messages[1]["content"]
    assert "[ITSC 3160]" in user and "[15-1242.00]" in user
    assert "Should Never Appear" not in user
    assert NOT_FOUND in messages[0]["content"]


def test_generate_refuses_non_local_models():
    with pytest.raises(ValueError):
        generate([{"role": "user", "content": "hi"}], model="gpt-4o")
