"""Concept-map CSVs become graph data for the frontend."""
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import concept_maps

MAP_DIR = Path(__file__).resolve().parents[1] / "data" / "syllabCMap"


@pytest.fixture
def client(monkeypatch):
    if not (MAP_DIR / "ITSC_3160").is_dir():
        pytest.skip("data/syllabCMap not present")
    monkeypatch.setenv("SYLLAB_MAP_DIR", str(MAP_DIR))
    app = FastAPI()
    app.include_router(concept_maps.router)
    return TestClient(app)


def test_lists_courses(client):
    courses = client.get("/concept-maps").json()["courses"]
    assert "ITSC_3160" in courses
    assert courses == sorted(courses)


def test_graph_has_nodes_for_every_edge_end(client):
    graph = client.get("/concept-maps/ITSC_3160").json()
    assert graph["course"] == "ITSC_3160"
    ids = {node["id"] for node in graph["nodes"]}
    assert graph["edges"], "ITSC_3160 has triples"
    for edge in graph["edges"]:
        assert edge["source"] in ids and edge["target"] in ids
        assert edge["predicate"] in {"PART_OF", "PREREQUISITE_OF", "USED_FOR", "SUBTYPE_OF"}
    assert {node["status"] for node in graph["nodes"]} <= {"verified", "inferred"}


def test_accepts_spaced_code_and_rejects_bad_codes(client):
    assert client.get("/concept-maps/itsc 3160").status_code == 200
    assert client.get("/concept-maps/..%2Fetc").status_code in {404, 422}
    assert client.get("/concept-maps/NOPE").status_code == 422
    assert client.get("/concept-maps/ZZZZ_9999").status_code == 404


def test_quoted_csv_fields_parse(tmp_path, monkeypatch):
    folder = tmp_path / "ABC_1000"
    folder.mkdir()
    (folder / "ABC_1000_concepts.csv").write_text(
        "course,type,term,as_in_text,occurrences,status,extracted_as,source_file\n"
        'ABC_1000,topic,"Diversity, Equity",x,2,verified,x,f\n'
        "ABC_1000,concept,graphs,x,1,inferred,x,f\n"
    )
    (folder / "ABC_1000_triples.csv").write_text(
        "course,subject,subject_type,predicate,object,object_type,order_evidence,flags,source_file\n"
        'ABC_1000,graphs,concept,PART_OF,"Diversity, Equity",topic,,,f\n'
        "ABC_1000,trees,concept,SUBTYPE_OF,graphs,concept,,,f\n"
    )
    monkeypatch.setenv("SYLLAB_MAP_DIR", str(tmp_path))
    graph = concept_maps.load_map("ABC_1000")
    labels = {node["label"]: node for node in graph["nodes"]}
    assert labels["Diversity, Equity"]["status"] == "verified"
    assert labels["trees"]["status"] == "inferred"  # only named by a triple
    assert len(graph["edges"]) == 2
