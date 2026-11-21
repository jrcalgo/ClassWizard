"""End-to-end evaluation of /explain: retrieval, generation and citations.

Reads an evaluation set (audit + questions, see tests/eval/explain_eval.json)
on stdin, runs every question through the same steps as POST /explain
(recommend -> retrieve_evidence -> build_messages -> generate ->
check_citations), and scores each answer automatically:

  retrieval   every id in expect_evidence was retrieved
  cites       the answer cites at least one id in expect_cite_any
  valid       no cited id is missing from the evidence (no made-up citations)
  grounded    check_citations() accepted the answer (what the app shows)
  refusal     expect_not_found items reply "not found in the data";
              all other items must NOT refuse (false refusals count)
  rules       every `require` regex matches and no `forbid` regex matches
  length      at most 4 sentences, as the system prompt demands
  all_cited   every sentence of a non-refusal answer carries a [citation]
              (stricter than check_citations(), which needs only one)

An item passes when every check that applies to it passes.

--judge adds a faithfulness check: the same local Ollama model reads the
evidence and the answer and labels each answer sentence supported or not.
Reported as the share of supported sentences. It is a second opinion from a
small model, so read the flagged sentences rather than trusting the number
alone. Nothing leaves the machine (FERPA guard in rag.py).

Run from the repo root with the stack up:
    docker compose exec -T backend python3 -m ai.nlp.explanations.evaluate < tests/eval/explain_eval.json
    ... evaluate --judge --only N01,X03 --json /data/out/explain_eval_results.json
The backend image copies the code at build time: after editing this file or
the pipeline, rebuild (docker compose up -d --build backend) before running.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

from ai.nlp.explanations.rag import (
    NOT_FOUND,
    build_messages,
    check_citations,
    generate,
    keep_cited,
    model_name,
    split_sentences,
    student_context,
)

RECOMMEND_LIMIT = 25  # same as backend.main._MAX_LIMIT
_CITED = re.compile(r"\[[^\[\]]+\]")

JUDGE_PROMPT = """You check whether an answer is supported by evidence.
For EACH sentence of the answer, decide if the evidence items explicitly support
every factual claim in that sentence. A sentence that only says the evidence does
not answer the question counts as supported.
Reply with JSON only, in this shape:
{"sentences": [{"sentence": "...", "supported": true, "reason": "short"}]}"""


def sentences(text: str) -> list[str]:
    return split_sentences(text)


def score(item: dict, evidence: list[dict], answer: str, checked: dict) -> dict:
    """Pass/fail for every check that applies to this item."""
    ids = {e["id"] for e in evidence}
    refused = NOT_FOUND in (answer or "").lower()
    checks: dict[str, bool] = {}
    if item.get("expect_evidence"):
        checks["retrieval"] = all(i in ids for i in item["expect_evidence"])
    if item.get("expect_cite_any") and not item.get("expect_not_found"):
        checks["cites"] = any(c in checked["citations"] for c in item["expect_cite_any"])
    checks["valid"] = not checked["unknown_citations"]
    checks["grounded"] = bool(checked["grounded"])
    checks["refusal"] = refused if item.get("expect_not_found") else not refused
    rules = [re.search(p, answer or "", re.I) is not None for p in item.get("require", [])]
    rules += [re.search(p, answer or "", re.I) is None for p in item.get("forbid", [])]
    if rules:
        checks["rules"] = all(rules)
    if answer and not refused:
        # The prompt asks for a citation after every claim. check_citations()
        # only needs one somewhere, so an uncited sentence still reads as grounded.
        checks["all_cited"] = all(_CITED.search(s) for s in sentences(answer))
    checks["length"] = len(sentences(answer)) <= 4
    return checks


def judge(evidence: list[dict], answer: str) -> list[dict]:
    """Label each answer sentence as supported or not, with the local model."""
    if not answer.strip():
        return []
    lines = "\n".join(f"[{e['id']}] {e['text']}" for e in evidence) or "(none)"
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {"role": "user", "content": f"Evidence:\n{lines}\n\nAnswer:\n{answer}"},
    ]
    raw = generate(messages)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        verdicts = json.loads(match.group(0))["sentences"] if match else []
    except (json.JSONDecodeError, KeyError, TypeError):
        verdicts = []
    return [v for v in verdicts if isinstance(v, dict) and "supported" in v]


def run_item(conn, audit: dict, item: dict, use_judge: bool) -> dict:
    from ai.nlp.explanations.retrieval import retrieve_evidence
    from ai.recommendations.ranking import recommend

    started = time.time()
    recommendation = recommend(conn, audit, item["soc_codes"], RECOMMEND_LIMIT)
    evidence = retrieve_evidence(conn, item["question"], audit, recommendation, item["soc_codes"])
    retrieved_at = time.time()
    messages = build_messages(item["question"], evidence, student_context(audit))
    try:
        raw, error = generate(messages), None
    except Exception as exc:  # report and keep going; one timeout should not end the run
        raw, error = "", f"{type(exc).__name__}: {exc}"
    finished = time.time()
    # Score what the student sees: POST /explain applies keep_cited() too.
    answer = keep_cited(raw) if error is None else ""
    checked = check_citations(answer, evidence)
    checks = score(item, evidence, answer, checked) if error is None else {"generated": False}
    result = {
        "id": item["id"],
        "category": item["category"],
        "question": item["question"],
        "answer": answer,
        "raw_answer": raw,
        "dropped_sentences": len(split_sentences(raw)) - len(split_sentences(answer))
        if answer != NOT_FOUND else 0,
        "error": error,
        "evidence_ids": [e["id"] for e in evidence],
        "citations": checked["citations"],
        "unknown_citations": checked["unknown_citations"],
        "checks": checks,
        "passed": all(checks.values()),
        "retrieval_seconds": round(retrieved_at - started, 1),
        "generation_seconds": round(finished - retrieved_at, 1),
    }
    if use_judge and answer:
        verdicts = judge(evidence, answer)
        result["judge"] = verdicts
        result["supported_share"] = (
            sum(bool(v["supported"]) for v in verdicts) / len(verdicts) if verdicts else None
        )
    return result


def summarise(results: list[dict]) -> dict:
    def share(key: str) -> str:
        applicable = [r["checks"][key] for r in results if key in r["checks"]]
        return f"{sum(applicable)}/{len(applicable)}" if applicable else "-"

    by_category: dict[str, list[bool]] = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r["passed"])
    judged = [r["supported_share"] for r in results if r.get("supported_share") is not None]
    generation = sorted(r["generation_seconds"] for r in results)
    return {
        "model": model_name(),
        "items": len(results),
        "passed": sum(r["passed"] for r in results),
        "checks": {key: share(key) for key in
                   ("retrieval", "cites", "valid", "grounded", "all_cited", "refusal", "rules", "length")},
        "by_category": {k: f"{sum(v)}/{len(v)}" for k, v in by_category.items()},
        "faithfulness": round(sum(judged) / len(judged), 2) if judged else None,
        "generation_seconds_median": generation[len(generation) // 2] if generation else None,
        "generation_seconds_max": generation[-1] if generation else None,
    }


def main() -> None:
    import psycopg

    parser = argparse.ArgumentParser(description="Evaluate /explain end to end.")
    parser.add_argument("--judge", action="store_true", help="add the local-model faithfulness check")
    parser.add_argument("--only", help="comma-separated item ids to run")
    parser.add_argument("--json", help="also write full results to this path")
    args = parser.parse_args()

    data = json.load(sys.stdin)
    audit = data["audit"]
    items = data["items"]
    if args.only:
        wanted = set(args.only.split(","))
        items = [item for item in items if item["id"] in wanted]

    results = []
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for item in items:
            r = run_item(conn, audit, item, args.judge)
            results.append(r)
            failed = [k for k, ok in r["checks"].items() if not ok]
            status = "PASS" if r["passed"] else "FAIL " + ",".join(failed)
            print(f"{r['id']:4} {status:28} {r['generation_seconds']:6.1f}s  {r['question']}", flush=True)
            print(f"     answer: {r['answer'] or r['error']}", flush=True)
            if r.get("dropped_sentences"):
                print(f"     dropped {r['dropped_sentences']} uncited sentence(s); raw: {r['raw_answer']}", flush=True)
            print(f"     evidence: {r['evidence_ids']}  cited: {r['citations']}", flush=True)
            for v in r.get("judge", []):
                if not v["supported"]:
                    print(f"     UNSUPPORTED: {v.get('sentence')}  ({v.get('reason')})", flush=True)

    summary = summarise(results)
    print("\n" + json.dumps(summary, indent=2))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "results": results}, f, indent=1)


if __name__ == "__main__":
    main()
