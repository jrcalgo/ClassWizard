"""Prompt building, generation and citation checking for /explain (the "A" and "G" in RAG).

Separate from llm.py, which serves the /chat route and its hosted providers.

The language model only explains: rules and similarity already chose the
courses (/recommend), and retrieval already chose the evidence. The prompt
tells the model to answer only from that evidence and to cite evidence IDs
in square brackets; check_citations() then verifies every cited ID exists.

Generation goes through LiteLLM to a local Ollama server. Only model names
starting with "ollama/" or "ollama_chat/" are accepted, so a configuration
change cannot silently send prompts to a hosted service (FERPA guard).

Configuration (environment variables):
  EXPLAIN_MODEL    default "ollama_chat/qwen3:8b"
  OLLAMA_URL       default "http://ollama:11434", the bundled compose service;
                   set http://host.docker.internal:11434 to use Ollama on the host
  EXPLAIN_TIMEOUT  default 180 (seconds; CPU-only generation is slow). The
                   frontend waits 240 s, so keep this below that.
These do not reuse LLM_MODEL: that variable belongs to /chat (llm.py), whose
default is a hosted model this module refuses.
"""

from __future__ import annotations

import os
import re

DEFAULT_MODEL = "ollama_chat/qwen3:8b"
DEFAULT_OLLAMA_URL = "http://ollama:11434"
DEFAULT_TIMEOUT = 180
LOCAL_PREFIXES = ("ollama/", "ollama_chat/")
NOT_FOUND = "not found in the data"

# Only these audit fields may enter a prompt. Course codes arrive separately,
# inside the evidence. Names, student IDs and advisors are never included.
CONTEXT_FIELDS = ("level", "major", "catalog_year", "credits_applied", "credits_required")

SYSTEM_PROMPT = f"""You explain course recommendations to a university student.
Rules:
1. Use ONLY the evidence items provided. Do not add facts from memory.
2. After every claim, cite the evidence ID it comes from in square brackets, e.g. [ITSC 3160] or [15-1242.00].
3. If the evidence does not answer the question, reply exactly: "{NOT_FOUND}".
4. Never invent prerequisites, grades, schedules, or course content.
5. Prerequisite entries may list alternatives separately; do not claim a student is ineligible.
6. Answer in at most 4 sentences."""

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CITATION = re.compile(r"\[([^\[\]]+)\]")


def model_name() -> str:
    return os.environ.get("EXPLAIN_MODEL", DEFAULT_MODEL)


def student_context(audit: dict) -> dict:
    """The few audit fields the prompt may see (whitelist, not blacklist)."""
    return {key: audit[key] for key in CONTEXT_FIELDS if audit.get(key) not in (None, "")}


def build_messages(question: str, evidence: list[dict], context: dict) -> list[dict]:
    """System rules + one user message holding context, evidence and the question."""
    lines = [f"[{item['id']}] {item['text']}" for item in evidence]
    about = "; ".join(f"{key.replace('_', ' ')}: {value}" for key, value in context.items())
    user = (
        f"Student context: {about or 'none'}\n\n"
        "Evidence:\n" + ("\n".join(lines) if lines else "(none)") + "\n\n"
        f"Question: {question.strip()}"
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def strip_thinking(text: str) -> str:
    """Remove any <think>...</think> reasoning a thinking model emits before its answer."""
    return _THINK.sub("", text or "").strip()


def generate(messages: list[dict], model: str | None = None) -> str:
    """Call the local model through LiteLLM and return the answer text."""
    model = model or model_name()
    if not model.startswith(LOCAL_PREFIXES):
        raise ValueError(f"refusing non-local model {model!r}: only Ollama models are allowed")
    import litellm  # imported here: loading it is slow and only /explain needs it

    response = litellm.completion(
        model=model,
        api_base=os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL),
        messages=messages,
        temperature=0.1,
        timeout=int(os.environ.get("EXPLAIN_TIMEOUT", DEFAULT_TIMEOUT)),
    )
    return strip_thinking(response.choices[0].message.content)


def cited_ids(answer: str) -> list[str]:
    """IDs cited in square brackets, in order of first appearance.

    "[ITSC 3160, 15-1242.00]" counts as two citations.
    """
    found: list[str] = []
    for group in _CITATION.findall(answer or ""):
        for part in re.split(r"[;,]", group):
            cid = part.strip()
            if cid and cid not in found:
                found.append(cid)
    return found


def check_citations(answer: str, evidence: list[dict]) -> dict:
    """Compare the answer's citations with the evidence that was actually given."""
    known = {item["id"] for item in evidence}
    cited = cited_ids(answer)
    unknown = [cid for cid in cited if cid not in known]
    not_found = NOT_FOUND in (answer or "").lower()
    return {
        "citations": [cid for cid in cited if cid in known],
        "unknown_citations": unknown,
        # Grounded: every citation is real, and the answer either cites
        # something or explicitly says the evidence does not cover it.
        "grounded": not unknown and (bool(cited) or not_found),
    }
