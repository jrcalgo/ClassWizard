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


def test_generate_refuses_non_local_models(monkeypatch):
    monkeypatch.delenv("EXPLAIN_ALLOW_REMOTE", raising=False)
    with pytest.raises(ValueError):
        generate([{"role": "user", "content": "hi"}], model="gpt-4o")


def test_generate_allows_hosted_model_when_opted_in(monkeypatch):
    calls = {}

    class FakeLiteLLM:
        @staticmethod
        def completion(**kwargs):
            calls.update(kwargs)
            message = type("M", (), {"content": "answer [ITSC 3160]"})
            choice = type("C", (), {"message": message})
            return type("R", (), {"choices": [choice]})

    monkeypatch.setitem(__import__("sys").modules, "litellm", FakeLiteLLM)
    monkeypatch.setenv("EXPLAIN_ALLOW_REMOTE", "1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    model = "openrouter/meta-llama/llama-3.1-70b-instruct"
    assert generate([{"role": "user", "content": "hi"}], model=model) == "answer [ITSC 3160]"
    assert calls["model"] == model and calls["api_key"] == "test-key"
    assert "api_base" not in calls  # the Ollama URL is only used for Ollama models


def _fake_litellm(monkeypatch, content):
    """Stand-in for litellm that records the completion() keyword arguments."""
    import sys
    import types

    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        message = types.SimpleNamespace(content=content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(completion=completion))
    return calls


def test_generate_turns_thinking_off_by_default(monkeypatch):
    monkeypatch.delenv("EXPLAIN_THINK", raising=False)
    calls = _fake_litellm(monkeypatch, "<think>hidden</think>It covers SQL [ITSC 3160].")
    answer = generate([{"role": "user", "content": "hi"}], model="ollama_chat/qwen3:8b")
    assert answer == "It covers SQL [ITSC 3160]."
    assert calls[0]["think"] is False


def test_generate_allows_thinking_when_enabled(monkeypatch):
    monkeypatch.setenv("EXPLAIN_THINK", "true")
    calls = _fake_litellm(monkeypatch, "ok")
    generate([{"role": "user", "content": "hi"}], model="ollama_chat/qwen3:8b")
    assert calls[0]["think"] is True


def test_keep_cited_drops_uncited_sentences():
    from ai.nlp.explanations.rag import keep_cited

    assert keep_cited("It covers SQL [ITSC 3160]. It is a great course.") == "It covers SQL [ITSC 3160]."
    # A citation written after the period stays with its sentence.
    assert keep_cited("It covers SQL. [ITSC 3160]") == "It covers SQL. [ITSC 3160]"
    # Nothing cited (e.g. a prompt-injected poem) becomes the exact refusal.
    assert keep_cited("In silent halls where data streams,\nA world of tables") == NOT_FOUND
    assert keep_cited("The evidence does not say. Not found in the data.") == NOT_FOUND


def test_named_blocks_matches_requirement_names_loosely():
    from ai.nlp.explanations.retrieval import named_blocks

    audit = {
        "courses_completed": [{"code": "PHYS 2101"}],
        "courses_not_taken": [
            {"block": "Ethics", "course_codes": ["ITSC 3688"]},
            {"block": "Natural Science", "course_codes": ["BIOL 1110", "CHEM 1251", "PHYS 2101"]},
            {"block": "Mathematics Elective", "course_codes": ["MATH 2112", "STAT 3128"]},
            {"block": "Free Electives", "course_codes": []},
        ],
    }
    assert named_blocks("Which course do I need for the Ethics requirement?", audit) == [
        ("Ethics", ["ITSC 3688"])
    ]
    # Taken courses are left out; "sciences" and "math" match on their first letters.
    assert named_blocks("natural sciences options?", audit) == [("Natural Science", ["BIOL 1110", "CHEM 1251"])]
    assert named_blocks("Which math elective?", audit) == [
        ("Mathematics Elective", ["MATH 2112", "STAT 3128"])
    ]
    # A block with no listed courses, or one only half named, is not matched.
    assert named_blocks("any free elective on security?", audit) == []
    assert named_blocks("tell me about science fiction", audit) == []


def test_keep_cited_prefers_the_models_own_refusal():
    from ai.nlp.explanations.rag import keep_cited

    answer = (
        "The syllabus lists 5:30-8:15PM, Mondays [ITCS 4180]. That is a different course. "
        "Therefore the meeting time is not found in the data."
    )
    assert keep_cited(answer) == NOT_FOUND


AUDIT_CREDIT = {
    "classification": "Sophomore",
    "courses_completed": [{"code": "MATH 2164"}, {"code": "STAT 2122"}, {"code": "ITSC 2214"}],
    "courses_in_progress": [{"code": "ITSC 3155"}],
}


def test_credit_notes_warn_when_the_student_already_has_the_credit():
    from ai.nlp.explanations.retrieval import credit_notes

    desc = ("An overview of linear algebra. May not be taken for credit if credit has been "
            "received for both MATH 2164 and STAT 2122 .")
    notes = credit_notes("MATH 2112", desc, AUDIT_CREDIT)
    assert len(notes) == 1 and "may not receive credit for MATH 2112" in notes[0]
    assert "MATH 2164 and STAT 2122" in notes[0]
    # "both" needs every course; having only one is no restriction.
    one = {"courses_completed": [{"code": "MATH 2164"}]}
    assert credit_notes("MATH 2112", desc, one) == []
    # Other wordings need any one course; bare numbers inherit the subject.
    either = "Credit will not be given for MATH 1100 where credit has been given for MATH 2164 or 2171."
    assert credit_notes("MATH 1100", either, AUDIT_CREDIT) != []
    assert credit_notes("MATH 1100", "Covers algebra. Not for majors.", AUDIT_CREDIT) == []


def test_course_item_shows_the_catalog_rule_and_restriction():
    from ai.nlp.explanations.retrieval import _course_item

    row = (
        "Software Development Projects", "Team project.", 3, 3, "(3)",
        "ITSC 2214; and ITSC 3155, or ITIS 3300, or ITIS 3310; or permission of instructor.",
        "Senior standing or permission of department.",
    )
    text = _course_item("ITSC 4155", row, AUDIT_CREDIT, [], [], {}, {}, None)["text"]
    assert '"ITSC 2214; and ITSC 3155, or ITIS 3300, or ITIS 3310; or permission of instructor."' in text
    assert "has completed or is taking: ITSC 2214, ITSC 3155." in text
    assert "Not completed: ITIS 3300, ITIS 3310." in text
    assert 'Catalog restriction: "Senior standing or permission of department."' in text
    assert "class standing is Sophomore" in text
