"""Command line: ``python -m catalog_pipeline build --pdf-dir PDFS --catalog NAME --out OUT``."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .build import BuildRefused, build, report_dict, requisite_summary, write_outputs


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code (0 ok, 1 refused, 2 usage error)."""
    ap = argparse.ArgumentParser(prog="catalog_pipeline",
                                 description="Acalog course-description print-outs -> JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, text in (("build", "validate, then write all outputs"),
                       ("validate", "run the checks only; write validation_report.json")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--pdf-dir", type=Path, required=True, help="folder of ..._pgN.pdf files")
        p.add_argument("--catalog", required=True, help="e.g. 'Undergraduate 2026-2027'")
        p.add_argument("--out", type=Path, required=True, help="output folder")
        p.add_argument("--page-size", type=int, default=100,
                       help="courses per listing page (default 100)")
        p.add_argument("--allow-errors", action="store_true",
                       help="write output even if validation fails (not recommended)")
    args = ap.parse_args(argv)
    if not args.pdf_dir.is_dir():
        print(f"error: {args.pdf_dir} is not a folder", file=sys.stderr)
        return 2
    try:
        result = build(args.pdf_dir, args.catalog, page_size=args.page_size,
                       allow_errors=args.allow_errors or args.cmd == "validate")
    except BuildRefused as exc:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "validation_report.json").write_text(
            json.dumps(report_dict(exc.report), indent=1), encoding="utf-8")
        print(exc, file=sys.stderr)
        print(f"no course data written; see {args.out / 'validation_report.json'}", file=sys.stderr)
        return 1

    if args.cmd == "validate":
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "validation_report.json").write_text(
            json.dumps(report_dict(result.report), indent=1), encoding="utf-8")
        print("validation", "passed" if result.report.ok else "FAILED",
              f"({result.report.values_checked} values checked)")
        for err in result.report.all_errors()[:40]:
            print("  error:", err)
        return 0 if result.report.ok else 1

    paths = write_outputs(result, args.out)
    courses = result.courses["courses"]
    print(f"{len(courses)} courses from {len(result.courses['sources'])} pages; "
          f"{result.report.values_checked} values verified; {len(result.fixes)} hyphens restored")
    print("edges:", dict(Counter(e["type"] for e in result.edges["edges"])))
    print("requisites:", json.dumps(requisite_summary(courses)))
    print("review queue:", dict(Counter(r["severity"] for r in result.review)))
    for warn in result.report.warnings:
        print("  warning:", warn[:160])
    for path in paths:
        print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
