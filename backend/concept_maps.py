"""Course concept maps as graph data, read from data/syllabCMap.

Each course folder holds {CODE}_concepts.csv (the nodes) and {CODE}_triples.csv
(the edges). The frontend draws them as an interactive graph; inferred concepts
(status "inferred") are drawn with dashed outlines.
"""

from __future__ import annotations

import csv
import os
import re
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/concept-maps")

_CODE = re.compile(r"[A-Z]{2,5}_\d{4}[A-Z]?")
_DEFAULT_DIR = Path(__file__).resolve().parents[1] / "data" / "syllabCMap"


def map_dir() -> Path:
    return Path(os.environ.get("SYLLAB_MAP_DIR", str(_DEFAULT_DIR)))


def normalize_code(code: str) -> str:
    """'ITSC 3160' and 'itsc_3160' both become 'ITSC_3160'."""
    return code.strip().upper().replace(" ", "_")


@lru_cache(maxsize=4)
def _courses(root: str) -> tuple[str, ...]:
    path = Path(root)
    if not path.is_dir():
        return ()
    return tuple(
        sorted(
            entry.name
            for entry in path.iterdir()
            if entry.is_dir()
            and _CODE.fullmatch(entry.name)
            and (entry / f"{entry.name}_concepts.csv").is_file()
        )
    )


def list_courses() -> list[str]:
    return list(_courses(str(map_dir())))


def _key(term: str) -> str:
    return " ".join(term.split()).lower()


@lru_cache(maxsize=256)
def _load(root: str, code: str) -> dict | None:
    folder = Path(root) / code
    concepts = folder / f"{code}_concepts.csv"
    if not concepts.is_file():
        return None
    nodes: dict[str, dict] = {}
    with concepts.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            term = (row.get("term") or "").strip()
            if not term:
                continue
            key = _key(term)
            try:
                occurrences = int(row.get("occurrences") or 0)
            except ValueError:
                occurrences = 0
            if key in nodes:
                nodes[key]["occurrences"] += occurrences
                continue
            nodes[key] = {
                "id": key,
                "label": term,
                "type": (row.get("type") or "concept").strip() or "concept",
                "status": (row.get("status") or "verified").strip() or "verified",
                "occurrences": occurrences,
            }

    edges: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    triples = folder / f"{code}_triples.csv"
    if triples.is_file():
        with triples.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                subject = (row.get("subject") or "").strip()
                obj = (row.get("object") or "").strip()
                predicate = (row.get("predicate") or "").strip()
                if not subject or not obj or not predicate:
                    continue
                source, target = _key(subject), _key(obj)
                if source == target or (source, target, predicate) in seen:
                    continue
                seen.add((source, target, predicate))
                # Triples can name terms the concept list does not; add them as
                # inferred nodes so every edge has both ends.
                for key, term, kind in ((source, subject, row.get("subject_type")), (target, obj, row.get("object_type"))):
                    if key not in nodes:
                        nodes[key] = {
                            "id": key,
                            "label": term,
                            "type": (kind or "concept").strip() or "concept",
                            "status": "inferred",
                            "occurrences": 0,
                        }
                edges.append(
                    {
                        "id": f"e{len(edges)}",
                        "source": source,
                        "target": target,
                        "predicate": predicate,
                        "order_evidence": (row.get("order_evidence") or "").strip() or None,
                        "flags": (row.get("flags") or "").strip() or None,
                    }
                )
    return {"course": code, "nodes": list(nodes.values()), "edges": edges}


def load_map(code: str) -> dict | None:
    code = normalize_code(code)
    if not _CODE.fullmatch(code):
        return None
    return _load(str(map_dir()), code)


@router.get("")
def get_courses():
    return {"courses": list_courses()}


@router.get("/{code}")
def get_map(code: str):
    if not _CODE.fullmatch(normalize_code(code)):
        return JSONResponse({"detail": "invalid course code"}, status_code=422)
    graph = load_map(code)
    if graph is None:
        return JSONResponse({"detail": "concept map not found"}, status_code=404)
    return graph
