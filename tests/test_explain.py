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


@pytest.mark.parametrize('method,label', [('spark_hybrid', 'rating (0–5)'), ('cosine_similarity', 'cosine similarity')])
def test_course_evidence_labels_scoring_method(method, label):
    from ai.nlp.explanations.retrieval import _course_item
    item = _course_item('ITSC 3160', ('Databases', 'SQL', 3, 3, '3'), {}, [], [],
                        {'career': 4.5 if method == 'spark_hybrid' else .7},
                        {'career': 'Database Administrator'}, None, method)
    assert label in item['text']
    assert 'Database Administrator' in item['text']


def test_skill_evidence_absence_does_not_prohibit_supported_partial_answers():
    from ai.nlp.explanations.rag import SYSTEM_PROMPT
    assert 'any part of the question' in SYSTEM_PROMPT
    assert 'missing evidence means no career relevance' in SYSTEM_PROMPT
    assert 'without weights or scoring arithmetic' in SYSTEM_PROMPT


def test_named_course_does_not_receive_discovery_skill_matches(monkeypatch):
    import ai.nlp.explanations.retrieval as r
    monkeypatch.setattr(r,'encode',lambda _: [[0.]])
    monkeypatch.setattr(r,'to_pgvector',lambda _: 'vector')
    monkeypatch.setattr(r,'_ranked_by_question',lambda *args: [])
    monkeypatch.setattr(r,'_syllabus_search',lambda *args: [])
    monkeypatch.setattr(r,'_open_search',lambda *args: [('ITSC 1212',.9)])
    monkeypatch.setattr(r,'_course_rows',lambda *args: {
        'ITSC 3160':('Databases','SQL',3,3,'3'), 'ITSC 1212':('Programming','Code',3,3,'3')})
    monkeypatch.setattr(r,'_prerequisites',lambda *args: {})
    monkeypatch.setattr(r,'_syllabus_rows',lambda *args: {})
    monkeypatch.setattr(r,'_objectives',lambda *args: {})
    monkeypatch.setattr(r,'_career_items',lambda *args: [])
    captured=[]
    def matches(conn,catalog,courses,*args):
        captured.extend(courses)
        return []
    monkeypatch.setattr(r,'retrieve_match_items',matches)
    class Conn:
        def execute(self,*args): return self
        def fetchall(self): return [('ITSC',)]
    evidence=r.retrieve_evidence(Conn(),'Why ITSC 3160?',{},
        {'catalog':'UG','scoring_method':'spark_hybrid','recommendations':[]},['career'])
    assert captured==['ITSC 3160']
    assert any(i['id']=='ITSC 1212' for i in evidence)  # existing discovery facts preserved
    assert 'unavailable' in evidence[0]['text']
