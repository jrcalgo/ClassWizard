"""Unit tests for the /explain evaluation scoring (no model, no database).

Run from the repo root:
    python -m pytest tests/test_explain_eval.py
"""

import json
from pathlib import Path

from ai.nlp.explanations.evaluate import score, sentences, summarise
from ai.nlp.explanations.rag import check_citations

EVIDENCE = [
    {"id": "ITSC 4155", "kind": "course", "text": "ITSC 4155 Software Development Projects."},
    {"id": "15-1252.00", "kind": "career", "text": "Software Developers: ..."},
]


def _item(**overrides):
    item = {
        "id": "T",
        "category": "test",
        "question": "q",
        "expect_evidence": [],
        "expect_cite_any": [],
        "expect_not_found": False,
        "require": [],
        "forbid": [],
    }
    item.update(overrides)
    return item


def _score(item, answer):
    return score(item, EVIDENCE, answer, check_citations(answer, EVIDENCE))


def test_grounded_answer_passes_every_check():
    item = _item(expect_evidence=["ITSC 4155"], expect_cite_any=["ITSC 4155"], require=["team"])
    checks = _score(item, "It is a team project course [ITSC 4155].")
    assert checks == {
        "retrieval": True, "cites": True, "valid": True, "grounded": True,
        "refusal": True, "rules": True, "length": True, "all_cited": True,
    }


def test_made_up_citation_fails_valid_and_grounded():
    checks = _score(_item(), "It needs ITSC 9999 first [ITSC 9999].")
    assert checks["valid"] is False and checks["grounded"] is False


def test_refusal_expected_and_false_refusal():
    assert _score(_item(expect_not_found=True), "not found in the data")["refusal"] is True
    assert _score(_item(), "not found in the data")["refusal"] is False


def test_forbid_and_missing_retrieval():
    item = _item(expect_evidence=["ITCS 4152"], forbid=["Paris"])
    checks = _score(item, "Paris [15-1252.00].")
    assert checks["retrieval"] is False and checks["rules"] is False


def test_length_counts_sentences():
    assert len(sentences("One [A]. Two. Three? Four! Five.")) == 5
    assert _score(_item(), "One [ITSC 4155]. Two. Three. Four. Five.")["length"] is False


def test_summary_counts_only_applicable_checks():
    results = [
        {"category": "a", "passed": True, "checks": {"valid": True}, "generation_seconds": 2.0},
        {"category": "a", "passed": False, "checks": {"valid": False, "cites": False},
         "generation_seconds": 4.0},
    ]
    summary = summarise(results)
    assert summary["checks"]["valid"] == "1/2"
    assert summary["checks"]["cites"] == "0/1"
    assert summary["by_category"] == {"a": "1/2"}


def test_eval_set_is_well_formed():
    data = json.loads(Path("tests/eval/explain_eval.json").read_text(encoding="utf-8"))
    ids = [item["id"] for item in data["items"]]
    assert len(ids) == len(set(ids))
    for item in data["items"]:
        assert item["question"].strip() and item["soc_codes"]
        assert not (item["expect_not_found"] and item["expect_cite_any"])


def test_all_cited_flags_an_uncited_sentence():
    assert _score(_item(), "It is a project course [ITSC 4155]. It is fun.")["all_cited"] is False
    assert _score(_item(), "Projects [ITSC 4155]. Careers [15-1252.00].")["all_cited"] is True
    assert "all_cited" not in _score(_item(expect_not_found=True), "not found in the data")
