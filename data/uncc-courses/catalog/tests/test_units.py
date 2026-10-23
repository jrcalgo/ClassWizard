"""Parser, repair, normalizers, relations and validation on small hand-made inputs."""
# pylint: disable=missing-function-docstring,redefined-outer-name
from pathlib import Path

from catalog_pipeline import normalize as N
from catalog_pipeline.extract import PageSource, parse_pdf_date, strip_furniture
from catalog_pipeline.parse import RawCourse, parse_pages
from catalog_pipeline.relations import exclusion_edges, finish_edges
from catalog_pipeline.repair import repair_page
from catalog_pipeline.validate import check_page

# A fragment shaped like pdftotext output of a print-out, page furniture included.
PAGE = """Course Descriptions - University of North Carolina at Charlotte

1 of 2

https://catalog.charlotte.edu/content.php?catoid=42&catoid=42&navoi...

Undergraduate Catalog | 2026-2027
Course Descriptions
Contract All Courses |
Print this Page
Schedule of Classes
Register for Courses in My UNC Charlotte
DegreeWorks

Geology
GEOL 3190 - Environmental Geology
Aspects of geology with direct or indirect impact on society.

Credit Hours: (3)
Prerequisite(s): GEOL 1200
and GEOL 1200L

10/1/2026, 2:43 PM

Schedule of Classes

GEOL 4364 - Aging and Criminal Justice: An Interdisciplinary
Understanding
Explores three-
dimensional thinking.
Credit Hours: (1 to 3) (SL)
Gerontology
GRNT 2100 - Introduction to Aging
Overview.Credit Hours: (3)
Page: 1 <- Back 10 … 1 | 2 | 3
"""


def test_parse_fragment():
    recs = parse_pages([(1, PAGE)])
    assert [r.code for r in recs] == ["GEOL 3190", "GEOL 4364", "GRNT 2100"]
    first, second, third = recs[0], recs[1], recs[2]
    assert first.section == "Geology" and first.fields["Prerequisite(s)"] == "GEOL 1200 and GEOL 1200L"
    assert second.title == "Aging and Criminal Justice: An Interdisciplinary Understanding"
    assert third.section == "Gerontology"              # heading between two courses
    assert third.description == "Overview." and third.fields["Credit Hours"] == "(3)"


def test_repair_only_where_reference_agrees():
    recs = [RawCourse(1, "AAAA", "1000", "T", None, "Explore threedimensional forms."),
            RawCourse(1, "AAAA", "1001", "T", None, "A threedimensional word typed this way.")]
    reference = "Explore three-\ndimensional forms.\nA threedimensional word typed this way."
    fixes = repair_page(recs, reference)
    assert recs[0].description == "Explore three-dimensional forms."
    assert recs[1].description == "A threedimensional word typed this way."   # source spelling
    assert [f.code for f in fixes] == ["AAAA 1000"]


def test_credit_hours():
    assert N.credit_hours("(3)")["min"] == 3
    c = N.credit_hours("(1 to 4) (SL)")
    assert (c["min"], c["max"], c["variable"], c["attributes"]) == (1, 4, True, ["SL"])
    assert N.credit_hours("(3 or 6)")["options"] == [3, 6]
    assert N.credit_hours("(3) (O,W)")["attributes"] == ["O", "W"]
    for bad in ("(!)", "(1 ro 3)", ""):
        assert N.credit_hours(bad)["status"] == "invalid"


def test_gen_ed_split():
    g = N.gen_ed("Oral Communication (O), Writing in the Disciplines (W)")
    assert [x["label"] for x in g["labels"]] == ["Oral Communication (O)", "Writing in the Disciplines (W)"]
    g = N.gen_ed("Local Arts/Humanities - Western Tradition")
    assert g["labels"][0]["components"] == ["Local Arts/Humanities", "Western Tradition"]


def test_repeatability():
    assert N.repeatability("No")["repeatable"] is False
    r = N.repeatability("May be repeated for credit up to 6 credit hours.")
    assert (r["repeatable"], r["max_credit_hours"]) == (True, 6)
    assert N.repeatability("May not be repeated for grade replacement.")["repeatable"] is None


def test_grading_and_crosslist():
    assert N.grading_method("Graded on a Pass/No Credit basis.")["method"] == "pass_no_credit"
    assert N.grading_method("Face-to-Face Instruction")["status"] == "delivery_mode_in_grading_field"
    x = N.cross_listed("HONR 3700 -H01 and LEGL 3354")
    assert x["courses"] == [{"code": "HONR 3700", "section": "H01"},
                            {"code": "LEGL 3354", "section": None}]


def test_restrictions():
    r = N.restrictions("Criminal Justice major or minor; and Junior or Senior standing.")
    assert r["gates"] == ["program", "standing"] and r["standing_levels"] == ["junior", "senior"]
    gpa = N.restrictions("minimum overall GPA of 2.8 and Biology GPA of 3.0")
    assert gpa["min_gpa_values"] == [2.8, 3.0]


def test_exclusions_and_reciprocity():
    text = ("Intro. May not be taken for credit and for a grade if credit has been "
            "received for ANTH 1501 .")
    e1 = exclusion_edges("ANTH 1101", [("description", text)])
    e2 = exclusion_edges("ANTH 1501", [("description", "May not be taken for credit if credit "
                                                       "has been received for ANTH 1101.")])
    edges = finish_edges(e1 + e2, {"ANTH 1101", "ANTH 1501"})
    assert len(edges) == 2 and all(e["reciprocal"] and e["target_resolved"] for e in edges)


def test_pdf_date_and_furniture():
    assert parse_pdf_date("D:20261001144423-04'00'") == "2026-10-01T14:44:23-04:00"
    assert strip_furniture(["12 of 47 10/1/2026, 9:56 AM", "keep"]) == ["keep"]


def test_page_without_text_is_refused():
    """The first page 18 print had its text drawn as shapes: no text layer at all."""
    src = PageSource(Path("x_pg18.pdf"), 18, "", "", 10, "Microsoft: Print To PDF", None, None, 0)
    report, _ = check_page(src, [], is_last=False, page_size=100)
    assert report.errors and "no usable text layer" in report.errors[0]
