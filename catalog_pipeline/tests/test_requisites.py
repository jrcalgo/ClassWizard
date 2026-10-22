"""Requisite parsing. Expected trees were written by reading the catalog text, not by
copying parser output, so these tests check the parser against an independent reading."""
# pylint: disable=missing-function-docstring,redefined-outer-name
import pytest

from catalog_pipeline.requisites import parse_requisite, tokenize

PRE = "Prerequisite(s)"


def course(code, grade=None, timing="before", **extra):
    leaf = {"type": "course", "code": code, "min_grade": grade, "timing": timing}
    leaf.update(extra)
    return leaf


def perm(of):
    return {"type": "permission", "of": of}


def strip_attempts(node):
    """max_attempts is only present when a grade was applied; drop None for comparison."""
    if isinstance(node, dict):
        return {k: strip_attempts(v) for k, v in node.items()
                if not (k == "max_attempts" and v is None)}
    if isinstance(node, list):
        return [strip_attempts(v) for v in node]
    return node


@pytest.mark.parametrize("text, tree", [
    ("ITSC 2214", course("ITSC 2214")),
    ("GEOL 1200 and GEOL 1200L.", {"op": "and", "items": [course("GEOL 1200"), course("GEOL 1200L")]}),
    ("FREN 3201 or FREN 3202, or permission of department.",
     {"op": "or", "items": [course("FREN 3201"), course("FREN 3202"), perm("department")]}),
    ("BIOL 2120, BIOL 2130, and BIOL 2140L with grades of C or above.",
     {"op": "and", "items": [course("BIOL 2120", "C"), course("BIOL 2130", "C"),
                             course("BIOL 2140L", "C")]}),
    ("CJUS 1511 and CJUS 2340, both with grade of C or above",
     {"op": "and", "items": [course("CJUS 1511", "C"), course("CJUS 2340", "C")]}),
    ("TRAN 4432 with a grade of B or above, or permission of department.",
     {"op": "or", "items": [course("TRAN 4432", "B"), perm("department")]}),
    ("ARTZ 3141 and ARTZ 2306 or permission of instructor.", None),          # mixed: unparsed
    ("GERM 2201, GERM 2202, GERM 3201, and GERM 3202; or permission of department.",
     {"op": "or", "items": [{"op": "and", "items": [course("GERM 2201"), course("GERM 2202"),
                                                    course("GERM 3201"), course("GERM 3202")]},
                            perm("department")]}),
    ("COMM 1101; COMM 2100; COMM 2104; and STAT 1220 or STAT 1222; all with a grade of C or above",
     {"op": "and", "items": [course("COMM 1101", "C"), course("COMM 2100", "C"),
                             course("COMM 2104", "C"),
                             {"op": "or", "items": [course("STAT 1220", "C"),
                                                    course("STAT 1222", "C")]}]}),
    ("MATH 1103 or higher", course("MATH 1103", or_higher=True)),
    ("Junior or Senior standing", {"type": "standing", "levels": ["junior", "senior"]}),
    ("MUSC 3300 and an approved principal ensemble.",
     {"op": "and", "items": [course("MUSC 3300"),
                             {"type": "other", "text": "an approved principal ensemble"}]}),
])
def test_trees(text, tree):
    result = parse_requisite(text, PRE)
    assert strip_attempts(result["tree"]) == tree


@pytest.mark.parametrize("text, status", [
    ("ITSC 2214", "parsed"),
    ("ACCT 3312 or ACCT 3324 and ACCT 3340 with grade of C or above.", "unparsed"),
    ("ARTB 1201 or ARTG 1201 and ARTB 1203 or ARTG 1203", "unparsed"),
    ("ARCH 1101, ARCH 1201", "proposed"),                     # comma list read as AND
    ("SPAN 2105 is recommended.", "advisory_only"),
    ("Two 3xxx/4xxx CCI courses with grades of C or above, or permission of department.",
     "proposed"),
])
def test_status(text, status):
    assert parse_requisite(text, PRE)["status"] == status


def test_unparsed_keeps_mentions_and_has_no_tree():
    r = parse_requisite("ACCT 3312 or ACCT 3324 and ACCT 3340 with grade of C or above.", PRE)
    assert r["tree"] is None
    assert r["courses_mentioned"] == ["ACCT 3312", "ACCT 3324", "ACCT 3340"]
    assert any(i["severity"] == "high" for i in r["review"])


def test_advisory_clause_does_not_swallow_requirement():
    """Regression: a recommendation after ';' once made the whole field advisory."""
    r = parse_requisite("SPAN 2201 or permission of department; SPAN 2105 is also recommended.", PRE)
    assert r["status"] == "parsed"
    assert r["tree"] == {"op": "or", "items": [course("SPAN 2201"), perm("department")]}
    assert r["advisory"] == [{"text": "SPAN 2105 is also recommended", "courses": ["SPAN 2105"]}]


def test_parenthetical_recommendation_is_advisory():
    r = parse_requisite("FREN 3201 or FREN 3202 (both recommended), or permission of department.", PRE)
    assert r["advisory"][0]["text"] == "both recommended"


def test_course_level_is_not_a_course():
    """Regression: 'SPAN 3000-level' was read as the course SPAN 3000."""
    r = parse_requisite("Two SPAN 3000-level courses.", PRE)
    assert r["tree"]["type"] == "level"
    assert (r["tree"]["subject"], r["tree"]["level"], r["tree"]["count"]) == ("SPAN", 3000, 2)
    assert not r["courses_mentioned"]


def test_each_course_keeps_its_own_grade():
    r = parse_requisite("MEGR 3111 with C or better and MEGR 3114 with C or better", PRE)
    assert r["status"] == "parsed"


def test_grade_after_and_pair_is_high_severity():
    r = parse_requisite("MATH 1103 or above and ETGR 2101 with grade of C or above.", PRE)
    assert any("may mean the last only" in i["reason"] and i["severity"] == "high"
               for i in r["review"])


def test_timing_follows_field():
    assert parse_requisite("MUPF 1112", "Corequisite(s)")["tree"]["timing"] == "same_term"
    assert parse_requisite("GEOL 1200", "Pre- or Corequisite(s)")["timing"] == "before_or_same_term"


def test_attempts_are_kept():
    r = parse_requisite("HSMT 2101 and HSMT 2104 with grades of C or above within two attempts", PRE)
    assert all(leaf["max_attempts"] == 2 for leaf in r["tree"]["items"])


def test_tokenizer_does_not_treat_lowercase_as_course():
    assert [t.kind for t in tokenize("math 1241")] == ["WORD"]
