"""Parsing of structured syllabus records (no database).

Run from the repo root:
    python -m pytest tests/test_syllabus_records.py
"""

from backend.storage.database.syllabus_records import clean_title, course_code_from_name, parse_record

RECORD = {
    "code": "ITSC 6160",  # the file name wins: one syllabus can serve two course numbers
    "title": "Database Systems (3 credit hours)",
    "level": "",
    "description": "  Relational   design and SQL. ",
    "prerequisites": "ITSC 3160 or ITCS 3160 with a grade of C",
    "cross_listed": ["ITCS 8160", "CRN 1650"],
    "units": [
        {"number": 1, "title": "Modeling", "source": "llm-inferred",
         "concepts": [{"label": "ER diagrams"}, {"label": "ER diagrams"}, {"label": "Keys"}]},
        {"number": 1, "title": "Duplicate number", "source": "syllabus-schedule", "concepts": []},
        {"number": 2, "title": "Queries", "source": "syllabus-schedule", "concepts": [{"label": "Joins"}]},
    ],
    "objectives": [
        {"id": "LO1", "text": "Design a normalized schema.", "bloom": "create"},
        {"id": "LO1", "text": "Write SQL queries.", "bloom": "apply"},
        {"id": "LO3", "text": "   ", "bloom": None},
    ],
}


def test_course_row_uses_file_name_and_cleans_fields():
    rows = parse_record("ITCS_8160.json", RECORD)
    code, title, description, level, prerequisites, cross_listed, source = rows["course"]
    assert code == "ITCS 8160" and source == "ITCS_8160.json"
    assert title == "Database Systems"
    assert description == "Relational design and SQL."
    assert level == "graduate"  # no level given: 8160 is a graduate number
    assert cross_listed == []  # itself and the CRN number are dropped
    assert rows["prerequisites"] == [("ITCS 8160", "ITSC 3160"), ("ITCS 8160", "ITCS 3160")]


def test_units_concepts_and_objectives_are_deduplicated():
    rows = parse_record("ITCS_8160.json", RECORD)
    assert rows["units"] == [("ITCS 8160", 1, "Modeling", True), ("ITCS 8160", 2, "Queries", False)]
    assert [c[2] for c in rows["concepts"]] == ["ER diagrams", "Keys", "Joins"]
    assert [o[1] for o in rows["objectives"]] == ["LO1", "LO1-2"]


def test_chunks_cover_the_course_and_each_objective():
    chunks = parse_record("ITCS_8160.json", RECORD)["chunks"]
    assert chunks[0][:2] == ("syllabus_course", "ITCS 8160")
    assert "Units: Modeling (ER diagrams, Keys)" in chunks[0][2]
    assert [c[1] for c in chunks[1:]] == ["ITCS 8160#LO1", "ITCS 8160#LO1-2"]


def test_title_and_code_helpers():
    assert course_code_from_name("ADMN_8171.json") == "ADMN 8171"
    assert clean_title("Geotechnical Lab- Section L03- 2 Credit Hours") == "Geotechnical Lab- Section L03"
    assert clean_title("Sports Business Analytics | 3 Credit Hours") == "Sports Business Analytics"
    assert clean_title(None) is None
