"""Stage 6a: requisite text -> logic tree (layer C).

A requisite such as

    "FREN 3201 or FREN 3202, or permission of department."

becomes

    {"op": "or", "items": [course FREN 3201, course FREN 3202, permission(department)]}

Parsing follows the punctuation of the sentence, from the loosest separator to the tightest:

    sentence ('.')  >  semicolon (';')  >  comma (',')  >  'and' / 'or' words  >  operand

At each level the connector word that opens a later part ('..., or B') decides the
operator. The result's ``status`` says how much trust it deserves:

* ``parsed``        every grouping decision was forced by the text
* ``proposed``      a tree is given, but at least one decision was an inference or a part
                    was not understood; each is listed in ``review`` with a severity
                    (``low`` = the usual catalog convention, ``high`` = a real guess or gap)
* ``unparsed``      the grouping is genuinely ambiguous (e.g. 'A or B and C' with no
                    punctuation); no tree, only the courses mentioned
* ``advisory_only`` the field only recommends; nothing is required

Nothing in ``proposed`` (high) or ``unparsed`` should be trusted until a person checks it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .constants import COURSE_CODE, REQUISITE_FIELDS

# ------------------------------------------------------------------ tokens

# 'with grades of C or above', 'both with a grade of C or better', 'with a grade B or above',
# '... within two attempts'
GRADE_RE = (r"(?:(?P<scope>all|both|each)\s+)?(?:with\s+|earn\s+)?(?:an?\s+)?(?:minimum\s+)?"
            r"(?P<plural>grades?)\s+(?:of\s+)?(?:at\s+least\s+)?(?:an?\s+)?\"?(?P<g>[ABCD][+-]?)"
            r"\"?(?:\s+(?:or|and)\s+(?:above|better|higher))?"
            r"(?:\s+within\s+(?P<att>one|two|three)\s+attempts)?")
# 'with C or better', '(C or better)' - no word 'grade'
BARE_GRADE_RE = r"\(?(?:with\s+)?(?:an?\s+)?\b(?P<bg>[ABCD][+-]?)\s+(?:or|and)\s+(?:above|better|higher)\b\)?"

TOKEN_SPEC = [
    ("NOF", r"(?:at least |any )?(?:one|two|three|four)(?: courses?)? (?:of|from) the following:?"),
    # 'two SPAN 3000-level courses', 'MUPF 32xx', 'any 3000-level course' - a level, not a course
    ("LEVEL", r"(?:(?:at least |any )?(?P<cnt>one|two|three|four)\s+)?(?:(?P<subj>[A-Z]{3,5})\s+)?"
              r"(?P<lvd>\d)(?:(?P<lv2>\d)xx|xxx|000\s*-?\s*level)(?:\s+courses?)?(?=$|[\s,;.)/])"),
    ("COURSE_UP", COURSE_CODE + r"\s+or\s+(?:above|higher)\b"),      # 'MATH 1103 or higher'
    ("COURSE", COURSE_CODE),
    ("GRADE", GRADE_RE),
    ("BARE_GRADE", BARE_GRADE_RE),
    ("OTHER", r"(?:an\s+)?approved principal ensemble|AAS degree"),
    ("PERMISSION", r"(?:the\s+)?(?:written\s+)?(?:permission|consent|approval)\s+(?:of|from|by)"
                   r"\s+(?:the\s+)?(?P<by>[A-Za-z][A-Za-z ]*?)(?=$|[,;()]|\s+or\b|\s+and\b)"),
    ("PLACEMENT", r"(?P<test>Math(?:ematics)?|Chemistry|English|Language)\s+Placement"
                  r"(?:\s+(?:Level|Test))?(?:\s+(?:Level\s+)?(?P<lvl>\d))?"),
    ("STANDING", r"(?P<lv>(?:Freshman|Sophomore|Junior|Senior)(?:(?:,\s*|\s+or\s+|,\s+or\s+)"
                 r"(?:Freshman|Sophomore|Junior|Senior))*)\s+standing"),
    ("EQUIV", r"(?:the\s+|an\s+|its\s+)?equivalents?(?:\s+(?:[a-z]+\s+)?courses?)?"),
    ("ANDOR", r"and/or"),
    ("AND", r"and"),
    ("OR", r"or"),
    ("COMMA", r","),
    ("SEMI", r";"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("WORD", r"[^\s,;()]+"),
    ("SPACE", r"\s+"),
]
TOKEN_RE = re.compile("|".join(f"(?P<{name}>{pat})" for name, pat in TOKEN_SPEC), re.IGNORECASE)
TOKEN_NAMES = [name for name, _ in TOKEN_SPEC]
# Words with no logic in this position ('either A or B', 'both A and B').
FILLER = {"either", "both", "a", "an", "the", "completion", "of", "in", "successful",
          "satisfactory"}
ADVISORY_RE = re.compile(r"recommend|encourag|suggest|advis(?:ed|able)", re.IGNORECASE)
SENTENCE_SPLIT = re.compile(r"(?<=[a-z0-9)])\.\s+(?=[A-Z])")
WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4}

LOW, HIGH = "low", "high"


@dataclass
class Tok:
    """One token; ``value`` holds its parsed payload (a leaf, a grade, a count)."""

    kind: str
    text: str
    value: object = None


@dataclass
class Ctx:
    """What one parse learned about itself."""

    timing: str
    review: list[dict] = field(default_factory=list)
    ambiguous: bool = False

    def infer(self, reason: str, severity: str) -> None:
        """Record a decision the text did not force, or a part not understood."""
        if not any(r["reason"] == reason for r in self.review):
            self.review.append({"reason": reason, "severity": severity})


def _grade(letter: str, applies_to_all: bool = False, attempts: int | None = None) -> dict:
    return {"grade": letter.upper(), "all": applies_to_all, "attempts": attempts}


def _make_token(m: re.Match) -> Tok | None:  # pylint: disable=too-many-return-statements
    """Build the token for one regex match (None for whitespace and filler words)."""
    kind = next(name for name in TOKEN_NAMES if m.group(name) is not None)
    text = m.group(0)
    if kind in ("COURSE", "COURSE_UP") and not re.match(COURSE_CODE, text):
        kind = "WORD"                  # IGNORECASE would accept 'math 1241'; codes are uppercase
    if kind == "SPACE" or (kind == "WORD" and text.lower() in FILLER):
        return None
    if kind == "GRADE":
        return Tok("GRADE", text, _grade(m.group("g"),
                                         bool(m.group("scope")) or m.group("plural").lower() == "grades",
                                         WORD_NUM.get((m.group("att") or "").lower())))
    if kind == "BARE_GRADE":
        return Tok("GRADE", text, _grade(m.group("bg")))
    if kind == "COURSE_UP":
        return Tok("COURSE", re.match(COURSE_CODE, text).group(0), {"or_higher": True})
    if kind == "OTHER":
        return Tok("LEAF", text, {"type": "other", "text": text.strip()})
    if kind == "PERMISSION":
        return Tok("LEAF", text, {"type": "permission", "of": m.group("by").strip().lower()})
    if kind == "PLACEMENT":
        return Tok("LEAF", text, {"type": "placement", "test": m.group("test").lower(),
                                  "level": int(m.group("lvl")) if m.group("lvl") else None})
    if kind == "STANDING":
        levels = re.findall(r"Freshman|Sophomore|Junior|Senior", m.group("lv"), re.IGNORECASE)
        return Tok("LEAF", text, {"type": "standing", "levels": [w.lower() for w in levels]})
    if kind == "EQUIV":
        return Tok("LEAF", text, {"type": "equivalent"})
    if kind == "LEVEL":
        return _level_token(m, text)
    if kind == "NOF":
        return Tok("NOF", text, WORD_NUM[re.search(r"one|two|three|four", text, re.I).group(0).lower()])
    if kind == "ANDOR":
        return Tok("OR", text)         # 'A and/or B' is satisfied by either
    return Tok(kind, text)


def _level_token(m: re.Match, text: str) -> Tok:
    """'two SPAN 3000-level courses' -> level leaf; 'MUPF 32xx' -> subject + number prefix."""
    subj = m.group("subj")
    if subj and not subj.isupper():
        subj = None                    # IGNORECASE matched an ordinary word
    hundreds = m.group("lv2")
    leaf = {"type": "level", "subject": subj, "level": int(m.group("lvd")) * 1000,
            "number_prefix": f"{m.group('lvd')}{hundreds}" if hundreds else None,   # 'MUPF 32xx'
            "count": WORD_NUM.get((m.group("cnt") or "").lower()) or 1, "text": text.strip()}
    return Tok("LEAF", text, leaf)


def tokenize(text: str) -> list[Tok]:
    """Split a requisite string into tokens; adjacent unknown words merge into one WORD."""
    toks: list[Tok] = []
    for m in TOKEN_RE.finditer(text):
        tok = _make_token(m)
        if tok is None:
            continue
        if tok.kind == "WORD" and toks and toks[-1].kind == "WORD":
            toks[-1].text += " " + tok.text
            continue
        toks.append(tok)
    return toks


# ------------------------------------------------------------------ grouping

def group_parens(toks: list[Tok], ctx: Ctx) -> list[Tok]:
    """Replace '( ... )' with one GROUP token holding the parsed inner expression."""
    out: list[Tok] = []
    stack: list[list[Tok]] = []
    for tok in toks:
        if tok.kind == "LPAREN":
            stack.append(out)
            out = []
        elif tok.kind == "RPAREN" and stack:
            inner, out = out, stack.pop()
            if inner and inner[0].kind in ("AND", "OR"):   # 'A (or B)': connector sits inside
                out.append(inner.pop(0))
            if inner and all(t.kind == "WORD" for t in inner):
                out.append(Tok("NOTE", " ".join(t.text for t in inner)))   # '(Honors section)'
            elif inner:
                out.append(Tok("GROUP", "(...)", parse_semis(inner, ctx)))
        elif tok.kind == "RPAREN":
            ctx.infer("unbalanced ')'", HIGH)
        else:
            out.append(tok)
    while stack:
        ctx.infer("unbalanced '('", HIGH)
        out = stack.pop() + out
    return out


def split_on(toks: list[Tok], kind: str) -> list[list[Tok]]:
    """Split a token list on a separator kind (COMMA or SEMI)."""
    parts: list[list[Tok]] = [[]]
    for tok in toks:
        if tok.kind == kind:
            parts.append([])
        else:
            parts[-1].append(tok)
    return [p for p in parts if p]


def make_node(op: str, items: list[dict]) -> dict:
    """An and/or node; children with the same operator are flattened into it."""
    flat: list[dict] = []
    for item in items:
        flat.extend(item["items"] if item.get("op") == op else [item])
    return {"op": op, "items": flat}


def apply_grade(node: dict, grade: dict) -> None:
    """Set a minimum grade on every course leaf under ``node`` that has none yet."""
    if node.get("type") in ("course", "level"):
        node["min_grade"] = node.get("min_grade") or grade["grade"]
        node["max_attempts"] = node.get("max_attempts") or grade["attempts"]
    for child in node.get("items", []):
        apply_grade(child, grade)


def combine(parts: list[list[Tok]], ctx: Ctx, level: str, sub) -> dict | None:
    """Join the parts of one separator level.

    A part that is only a grade ('; all with grades of C or above') applies to every part
    before it. Otherwise the connector opening a later part decides the operator.
    """
    connectors: list[str] = []
    nodes: list[dict] = []
    for idx, part in enumerate(parts):
        if idx and part and part[0].kind in ("AND", "OR"):
            connectors.append(part[0].kind.lower())
            part = part[1:]
        if part and all(t.kind == "GRADE" for t in part):
            if not nodes and not ctx.ambiguous:
                ctx.infer(f"grade '{part[0].text}' with no course before it", HIGH)
            if not part[-1].value["all"]:
                ctx.infer("grade after a list assumed to apply to every course before it", LOW)
            for node in nodes:
                apply_grade(node, part[-1].value)
            if connectors and idx == len(connectors):     # 'and with grades...' : not a part
                connectors.pop()
            continue
        node = sub(part, ctx)
        if node is not None:
            nodes.append(node)
    if not nodes:
        return None
    if len(nodes) == 1:
        return nodes[0]
    kinds = set(connectors)
    if len(kinds) > 1:
        ctx.ambiguous = True
        ctx.infer(f"both 'and' and 'or' join {level}-separated parts", HIGH)
        return None
    if not kinds:
        ctx.infer(f"{level}-separated list without 'and'/'or' read as AND", LOW)
    node = make_node(kinds.pop() if kinds else "and", nodes)
    # Semicolons separate groups unmistakably; a comma doing the same job is a reading.
    if level == "comma" and {n.get("op") for n in nodes if "op" in n} - {node["op"]}:
        ctx.infer("grouping taken from comma placement", LOW)
    return node


def parse_semis(toks: list[Tok], ctx: Ctx) -> dict | None:
    """Top level of an expression: parts separated by ';'."""
    if any(t.kind == "LPAREN" for t in toks):
        toks = group_parens(toks, ctx)
    if toks and toks[0].kind == "NOF":          # 'two of the following: A, B, C'
        return n_of(toks[0].value, parse_semis(toks[1:], ctx))
    return combine(split_on(toks, "SEMI"), ctx, "semicolon", parse_commas)


def n_of(n: int, inner: dict | None) -> dict:
    """'two of the following: A, B, C' -> n_of node over the listed items."""
    items = inner["items"] if inner and inner.get("op") in ("and", "or") else \
        ([inner] if inner else [])
    return {"op": "n_of", "n": n, "items": items}


def parse_commas(toks: list[Tok], ctx: Ctx) -> dict | None:
    """Middle level: parts separated by ','."""
    if toks and toks[0].kind == "NOF":          # '...; two courses from the following: A, B'
        return n_of(toks[0].value, parse_commas(toks[1:], ctx))
    parts = split_on(toks, "COMMA")
    trailing = None
    # 'A, B, and C with grades of C or above': a plural grade ending the last part
    # belongs to the whole list, not just to C.
    if len(parts) > 1 and parts[-1][-1].kind == "GRADE" and parts[-1][-1].value["all"] \
            and len(parts[-1]) > 1:
        trailing = parts[-1].pop().value
    node = combine(parts, ctx, "comma", parse_words)
    if node is not None and trailing:
        apply_grade(node, trailing)
    return node


def parse_words(toks: list[Tok], ctx: Ctx) -> dict | None:
    """Innermost level: operands joined by 'and' / 'or' with no punctuation in between."""
    operands: list[dict] = []
    ops: list[str] = []
    end_grade = lead_grade = None
    for i, tok in enumerate(toks):
        if tok.kind in ("AND", "OR"):
            ops.append(tok.kind.lower())
        elif tok.kind == "GRADE":
            if i == len(toks) - 1 and len(operands) > 1:
                end_grade = tok.value             # scope decided after the loop
            elif not operands:
                lead_grade = tok.value            # 'Grade of C or above in MUPF 3201'
            else:
                apply_grade(operands[-1], tok.value)
        elif tok.kind == "NOTE":
            attach_note(operands[-1] if operands else None, tok.text, ctx)
        else:
            operands.append(operand(tok, ctx))
    scope_grades(operands, ops, lead_grade, end_grade, ctx)
    if not operands:
        return None
    if len(operands) == 1:
        return operands[0]
    if len(set(ops)) > 1:
        ctx.ambiguous = True
        ctx.infer("'and' and 'or' mixed without punctuation; grouping unclear", HIGH)
        return None
    if len(ops) < len(operands) - 1:
        ctx.infer("operands with no connector between them read as AND", HIGH)
    return make_node(ops[0] if ops else "and", operands)


def scope_grades(operands: list[dict], ops: list[str], lead: dict | None, end: dict | None,
                 ctx: Ctx) -> None:
    """Decide which operands a grade written before or after them applies to."""
    if lead:                               # 'Grade of C or above in A and B'
        if len(operands) > 1:
            ctx.infer("grade written before several items assumed to apply to all", LOW)
        for leaf in operands:
            apply_grade(leaf, lead)
    if not end:
        return
    if any(o.get("min_grade") for o in operands[:-1]):
        apply_grade(operands[-1], end)     # 'A with C and B with C': each has its own
        return
    if not end["all"]:
        # 'A or B with C': only one is taken, so the grade covers either (usual reading).
        # 'A and B with C': last course only, or both? A real guess.
        if "and" in ops:
            ctx.infer("grade after 'A and B' applied to both; may mean the last only", HIGH)
        else:
            ctx.infer("grade after alternatives applied to each alternative", LOW)
    for leaf in operands:
        apply_grade(leaf, end)


CONDITIONAL_NOTE = re.compile(r"\bfor\b|program|major|only|students", re.IGNORECASE)


def attach_note(target: dict | None, note: str, ctx: Ctx) -> None:
    """Keep a parenthetical remark on the item it follows. Remarks that make the item
    conditional ('(for the B.A. in Chemistry program)') need a person to read them."""
    if target is None:
        ctx.infer(f"unrecognized text: '({note})'", HIGH)
        return
    target.setdefault("notes", []).append(note)
    if CONDITIONAL_NOTE.search(note):
        ctx.infer(f"conditional remark: '({note})'", HIGH)


def operand(tok: Tok, ctx: Ctx) -> dict:
    """The leaf (or already-parsed group) for one token."""
    if tok.kind == "COURSE":
        leaf = {"type": "course", "code": tok.text, "min_grade": None, "timing": ctx.timing}
        if tok.value and tok.value.get("or_higher"):
            leaf["or_higher"] = True             # 'MATH 1103 or higher': that course or a later one
        return leaf
    if tok.kind == "GROUP":
        return tok.value if tok.value is not None else {"type": "text", "text": tok.text}
    if tok.kind == "LEAF":
        if tok.value.get("type") == "level" and not tok.value["subject"]:
            ctx.infer(f"course level without a subject: '{tok.text.strip()}'", HIGH)
        return dict(tok.value)
    ctx.infer(f"unrecognized text: '{tok.text}'", HIGH)
    return {"type": "text", "text": tok.text}


# ------------------------------------------------------------------ entry point

def split_advisory(text: str) -> tuple[str, list[str]]:
    """Move recommendation-only parts out of the requirement: a parenthesis
    ('(both recommended)') or a whole sentence ('Statistics recommended.')."""
    advisory: list[str] = []

    def take(match: re.Match) -> str:
        if ADVISORY_RE.search(match.group(0)):
            advisory.append(match.group(0).strip(" ()"))
            return " "
        return match.group(0)
    text = re.sub(r"\([^()]*\)", take, text)
    kept = []
    for sentence in SENTENCE_SPLIT.split(text):
        clauses = []
        for clause in re.split(r"(?<=;)", sentence):        # keep the ';' on each clause
            if ADVISORY_RE.search(clause):
                advisory.append(clause.strip(" .;"))
            else:
                clauses.append(clause)
        joined = "".join(clauses).strip().rstrip(";").strip()
        if joined:
            kept.append(joined)
    return ". ".join(kept), advisory


MENTION_RE = re.compile(r"\b(" + COURSE_CODE + r")\b(?!\s*-\s*level)")


def mentioned_codes(text: str) -> list[str]:
    """Course codes in a text, in order, without duplicates; 'SPAN 3000-level' is a level."""
    return list(dict.fromkeys(MENTION_RE.findall(text)))


def parse_requisite(raw: str, field_name: str) -> dict:
    """Parse one requisite field value into the structured form described above."""
    ctx = Ctx(REQUISITE_FIELDS[field_name])
    text = raw.strip().replace("“", '"').replace("”", '"')
    text = re.sub(r"^(?:Prerequisites?|Corequisites?)\s*:\s*", "", text)  # label repeated in value
    requirement, advisory = split_advisory(text)
    sentences = [s.strip().rstrip(".") for s in SENTENCE_SPLIT.split(requirement.strip().rstrip("."))
                 if s.strip(" .")]
    tree = None
    if sentences:
        nodes = [n for n in (parse_semis(tokenize(s), ctx) for s in sentences) if n is not None]
        if len(sentences) > 1:
            ctx.infer("several sentences combined as AND", HIGH)
        if nodes and not ctx.ambiguous:
            tree = nodes[0] if len(nodes) == 1 else make_node("and", nodes)

    if not sentences and advisory:
        status = "advisory_only"
    elif ctx.ambiguous or tree is None:
        status, tree = "unparsed", None
    elif ctx.review:
        status = "proposed"
    else:
        status = "parsed"
    return {
        "raw": raw,
        "timing": ctx.timing,
        "status": status,
        "tree": tree,
        "advisory": [{"text": a, "courses": mentioned_codes(a)} for a in advisory],
        "courses_mentioned": mentioned_codes(raw),
        "review": ctx.review,
    }
