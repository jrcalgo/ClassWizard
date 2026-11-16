"""Tests for syllabi_pipeline/build_triples.py using a tiny made-up course.

Run from the repo root:
    python -m pytest tests/test_syllabi_pipeline.py
"""

import csv

from syllabi_pipeline.build_triples import build, canonical_id, discover, main

TRIPLE_HEADER = "course,subject,subject_type,predicate,object,object_type,order_evidence,flags,source_file\n"
CONCEPT_HEADER = "course,type,term,as_in_text,occurrences,status,extracted_as,source_file\n"


def make_course(root, course, triples, concepts):
    folder = root / course
    folder.mkdir(parents=True)
    (folder / f"{course}_triples.csv").write_text(TRIPLE_HEADER + "".join(triples), encoding="utf-8")
    (folder / f"{course}_concepts.csv").write_text(CONCEPT_HEADER + "".join(concepts), encoding="utf-8")


CONCEPTS = [
    "TEST_1000,concept,SQL,SQL,5,verified,SQL,x\n",
    "TEST_1000,topic,Databases,Databases,3,verified,Databases,x\n",
    "TEST_1000,tool,PostgreSQL,PostgreSQL,1,verified,PostgreSQL,x\n",
    "TEST_1000,concept,Joins,Joins,2,unverified,Joins,x\n",
    "TEST_1000,concept,Query Writing Tips,Query Writing Tips,1,inferred,Query Writing Tips,x\n",
    "TEST_1000,topic,Data Storage Basics,Data Storage Basics,1,inferred,Data Storage Basics,x\n",
]


def run(tmp_path, triples, **kwargs):
    make_course(tmp_path, "TEST_1000", triples, CONCEPTS)
    triple_files, concept_files = discover(tmp_path)
    result, _ = build(triple_files, concept_files, {"TEST 1000": "Intro to Data"}, **kwargs)
    return result


def relations(result):
    return [r for r in result.valid if r["predicate"] != "covers"]


def test_maps_vocabulary_and_builds_evidence(tmp_path):
    result = run(tmp_path, ["TEST_1000,SQL,concept,PREREQUISITE_OF,Databases,topic,A taught first,,x\n"])
    [row] = relations(result)
    assert row["predicate"] == "prerequisite_for"
    assert row["subject_type"] == "Concept" and row["object_type"] == "Topic"
    assert row["confidence"] == "0.90"
    assert row["filename"] == "TEST_1000.pdf"
    assert row["evidence"].startswith("In TEST 1000 (Intro to Data), SQL is a prerequisite for Databases")


def test_canonical_id_matches_existing_convention():
    # Existing data: "Agentic AI" (Technology) -> technology_f46237c0
    assert canonical_id("Technology", "  Agentic   AI ") == "technology_f46237c0"


def test_tool_becomes_technology(tmp_path):
    result = run(tmp_path, ["TEST_1000,PostgreSQL,tool,USED_FOR,Databases,topic,,,x\n"])
    [row] = relations(result)
    assert row["subject_type"] == "Technology"
    assert row["subject_canonical_id"].startswith("technology_")


def test_flagged_rows_go_to_review_unless_threshold_lowered(tmp_path):
    flagged = ["TEST_1000,Databases,topic,PREREQUISITE_OF,SQL,concept,B taught first,B is taught before A - check,x\n"]
    result = run(tmp_path, flagged)
    assert relations(result) == []
    assert result.reasons["flagged_for_review"] == 1

    result = run(tmp_path / "again", flagged, min_confidence=0.0)
    [row] = relations(result)
    assert row["confidence"] == "0.50"


def test_rejects_unknown_endpoints_unverified_and_bad_predicates(tmp_path):
    result = run(tmp_path, [
        "TEST_1000,SQL,concept,PART_OF,Not A Concept,topic,,,x\n",
        "TEST_1000,Joins,concept,PART_OF,SQL,concept,,,x\n",
        "TEST_1000,SQL,concept,TEACHES,Databases,topic,,,x\n",
        "TEST_1000,SQL,concept,PART_OF,sql,concept,,,x\n",
    ])
    assert relations(result) == []
    assert result.reasons["endpoint_not_in_concepts"] == 1
    assert result.reasons["endpoint_unverified"] == 1
    assert result.reasons["unknown_predicate:TEACHES"] == 1
    assert result.reasons["self_loop"] == 1


def test_covers_rows_for_verified_and_inferred_concepts(tmp_path):
    result = run(tmp_path, [])
    covers = [r for r in result.valid if r["predicate"] == "covers"]
    assert sorted(r["object"] for r in covers) == [
        "Data Storage Basics", "Databases", "PostgreSQL", "Query Writing Tips", "SQL",
    ]
    assert all(r["subject"] == "TEST 1000" and r["subject_type"] == "Course" for r in covers)
    by_obj = {r["object"]: r for r in covers}
    assert by_obj["SQL"]["confidence"] == "0.90" and by_obj["PostgreSQL"]["confidence"] == "0.80"
    assert by_obj["Query Writing Tips"]["confidence"] == "0.60"
    assert "inferred" in by_obj["Query Writing Tips"]["evidence"]
    assert result.reasons["concept_unverified"] == 1  # "unverified" is neither known status


def test_inferred_relations_capped_or_rejected(tmp_path):
    result = run(tmp_path, [
        "TEST_1000,SQL,concept,PART_OF,Data Storage Basics,topic,,,x\n",
        "TEST_1000,Query Writing Tips,concept,PART_OF,Data Storage Basics,topic,,,x\n",
    ])
    [row] = relations(result)
    assert row["object"] == "Data Storage Basics"
    assert row["confidence"] == "0.65"
    assert "Inferred, not quoted from the syllabus: Data Storage Basics" in row["evidence"]
    assert result.reasons["both_endpoints_inferred"] == 1

    kept = run(tmp_path / "pairs", [
        "TEST_1000,Query Writing Tips,concept,PART_OF,Data Storage Basics,topic,,,x\n",
    ], include_inferred_pairs=True)
    assert relations(kept)[0]["confidence"] == "0.60"


def test_no_inferred_drops_them_everywhere(tmp_path):
    result = run(tmp_path, ["TEST_1000,SQL,concept,PART_OF,Data Storage Basics,topic,,,x\n"],
                 include_inferred=False)
    assert relations(result) == []
    assert result.reasons["endpoint_inferred"] == 1
    assert result.reasons["concept_inferred"] == 2


def test_duplicates_are_dropped_and_ids_are_stable(tmp_path):
    row = "TEST_1000,SQL,concept,PART_OF,Databases,topic,,,x\n"
    first = run(tmp_path / "a", [row, row])
    second = run(tmp_path / "b", [row])
    assert first.reasons["duplicate"] == 1
    assert relations(first)[0]["triple_id"] == relations(second)[0]["triple_id"]


def test_cli_writes_csv_report_and_rejects(tmp_path):
    src = tmp_path / "in"
    make_course(src, "TEST_1000", ["TEST_1000,SQL,concept,PART_OF,Databases,topic,,,x\n"], CONCEPTS)
    out = tmp_path / "out" / "valid.csv"
    assert main(["--input", str(src), "--output", str(out), "--catalog", str(tmp_path / "none.csv")]) == 0
    with out.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 6  # 1 relation + 3 verified + 2 inferred concepts
    assert (out.parent / "pipeline_report.json").is_file()
    assert (out.parent / "rejected_triples.csv").is_file()
