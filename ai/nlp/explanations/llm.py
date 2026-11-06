"""Chat replies from an API endpoint or a LiteLLM subscription."""

from __future__ import annotations

import json
import os

import litellm

_COURSE_LISTS = (
    "courses_completed",
    "courses_in_progress",
    "courses_preregistered",
    "courses_not_taken",
)
_COPILOT_OPTIONAL = (
    "GITHUB_COPILOT_ACCESS_TOKEN_FILE",
    "GITHUB_COPILOT_API_KEY_FILE",
    "GITHUB_COPILOT_API_BASE",
)
_CLAUDE_LOGIN_ERROR = (
    "The host Claude login is not in /opt/claude/.credentials.json. "
    "On a Mac, Claude Code often keeps it in the keychain, which Docker cannot see."
)


def explain(
    question: str,
    history: list[dict],
    audit: dict,
    prefs: dict,
    rows: list[dict],
) -> str:
    """Return one reply. The audit name is not sent to the model."""
    messages = _messages(question, history, audit, prefs, rows)
    mode = _setting("LLM_MODE") or "api"
    if mode == "api":
        return _complete_api(messages)
    if mode == "subscription":
        return _complete_subscription(messages)
    raise RuntimeError("LLM_MODE must be api or subscription")


def _setting(name: str) -> str:
    return os.environ.get(name, "").strip()


def _model() -> str:
    model = _setting("LLM_MODEL")
    if not model:
        raise RuntimeError("LLM_MODEL is not set")
    return model


def _complete_api(messages: list[dict]) -> str:
    extra = {}
    if _setting("LLM_API_BASE"):
        extra["api_base"] = _setting("LLM_API_BASE")
    if _setting("LLM_API_KEY"):
        extra["api_key"] = _setting("LLM_API_KEY")
    response = litellm.completion(model=_model(), messages=messages, **extra)
    return _choice_text(response)


def _complete_subscription(messages: list[dict]) -> str:
    kind = _setting("LLM_SUBSCRIPTION")
    if kind == "copilot":
        return _complete_copilot(messages)
    if kind == "chatgpt":
        return _complete_chatgpt(messages)
    if kind == "claude":
        return _complete_claude(messages)
    raise RuntimeError("LLM_SUBSCRIPTION must be copilot, chatgpt, or claude")


def _complete_copilot(messages: list[dict]) -> str:
    for name in _COPILOT_OPTIONAL:
        if name in os.environ and not os.environ[name].strip():
            del os.environ[name]
    model = _model()
    if not model.startswith("github_copilot/"):
        model = f"github_copilot/{model}"
    response = litellm.completion(model=model, messages=messages)
    return _choice_text(response)


def _complete_chatgpt(messages: list[dict]) -> str:
    os.environ.setdefault("CHATGPT_TOKEN_DIR", "/opt/codex")
    os.environ.setdefault("CHATGPT_AUTH_FILE", "auth.json")
    model = _model()
    if not model.startswith("chatgpt/"):
        model = f"chatgpt/{model}"
    response = litellm.responses(model=model, input=messages)
    text = getattr(response, "output_text", None)
    if not text:
        raise RuntimeError("chatgpt subscription returned no text")
    return text


def _claude_credentials_path() -> str:
    return "/opt/claude/.credentials.json"


def _claude_oauth_token() -> str:
    path = _claude_credentials_path()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(_CLAUDE_LOGIN_ERROR) from exc
    oauth = data.get("claudeAiOauth") if isinstance(data, dict) else None
    token = oauth.get("accessToken") if isinstance(oauth, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError(_CLAUDE_LOGIN_ERROR)
    return token


def _complete_claude(messages: list[dict]) -> str:
    system, chat = _split_system(messages)
    model = _model()
    if not model.startswith("anthropic/"):
        model = f"anthropic/{model}"
    response = litellm.anthropic.messages.create(
        max_tokens=1024,
        messages=chat,
        model=model,
        system=system or None,
        api_key=_claude_oauth_token(),
    )
    return _anthropic_text(response)


def _choice_text(response) -> str:
    text = response.choices[0].message.content
    if not text:
        raise RuntimeError("model returned no text")
    return text


def _anthropic_text(response) -> str:
    blocks = getattr(response, "content", None) or []
    parts = []
    for block in blocks:
        text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
        if text:
            parts.append(text)
    if not parts:
        raise RuntimeError("claude subscription returned no text")
    return "".join(parts)


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    system = []
    chat = []
    for item in messages:
        if item.get("role") == "system":
            system.append(item.get("content") or "")
        else:
            chat.append(item)
    return "\n".join(part for part in system if part), chat


def _messages(
    question: str,
    history: list[dict],
    audit: dict,
    prefs: dict,
    rows: list[dict],
) -> list[dict]:
    prior = []
    for item in history[-8:]:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            prior.append({"role": role, "content": str(content)})
    user = (
        "Audit:\n"
        + json.dumps(_prompt_audit(audit))
        + "\nPreferences:\n"
        + json.dumps(prefs)
        + "\nRetrieved triples:\n"
        + json.dumps(_evidence(rows))
        + "\nQuestion:\n"
        + question.strip()
    )
    return [
        {"role": "system", "content": _system_prompt(audit)},
        *prior,
        {"role": "user", "content": user},
    ]


def _system_prompt(audit: dict) -> str:
    registered = (
        _codes(audit, "courses_completed")
        + _codes(audit, "courses_in_progress")
        + _codes(audit, "courses_preregistered")
    )
    listed = ", ".join(registered) if registered else "(none)"
    return (
        "Answer from the retrieved syllabus triples and the audit facts. "
        "Quote the evidence sentence you use. If the triples do not support "
        "a claim, say so. Do not use the student's name. Do not recommend a "
        "course code that is completed, in progress, or preregistered unless "
        "the question asks about that course. Those codes are: "
        + listed
        + "."
    )


def _prompt_audit(audit: dict) -> dict:
    kept = {
        "degree": audit.get("degree"),
        "level": audit.get("level"),
        "classification": audit.get("classification"),
        "program": audit.get("program"),
        "major": audit.get("major"),
        "college": audit.get("college"),
        "catalog_year": audit.get("catalog_year"),
        "credits_required": audit.get("credits_required"),
        "credits_applied": audit.get("credits_applied"),
    }
    for key in _COURSE_LISTS:
        kept[key] = audit.get(key) or []
    return kept


def _evidence(rows: list[dict]) -> list[dict]:
    return [
        {
            "subject": row.get("subject"),
            "predicate": row.get("predicate"),
            "object": row.get("object"),
            "evidence": row.get("evidence"),
            "filename": row.get("filename"),
            "similarity": row.get("similarity"),
        }
        for row in rows
    ]


def _codes(audit: dict, key: str) -> list[str]:
    rows = audit.get(key) or []
    return [row.get("code") for row in rows if row.get("code")]
