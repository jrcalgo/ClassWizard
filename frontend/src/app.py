import html
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

import streamlit as st

import chat
import recommend
import style
from uploads.degreeworks import AuditUnavailable, load_audit, post_audit, watch_session

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "classwizard-logo.png"
SYLLAB_MAP_DIR = Path(
    os.environ.get(
        "SYLLAB_MAP_DIR",
        str(Path(__file__).resolve().parent.parent.parent / "data" / "syllabCMap"),
    )
)
# "explain": chat answers come from /explain (cited, local Ollama).
# "chat": chat answers come from /chat (syllabus triples, LLM_MODEL provider).
CHAT_MODE = os.environ.get("CHAT_MODE", "explain").strip().lower()
RECOMMEND_LIMIT = 10

CURRENT_COURSES = ["ITSC 1212", "STAT 1220", "WRDS 1103"]
NEEDED_COURSES = ["ITSC 3160", "STAT 2122", "COMM 2100"]

TERMS = [
    {
        "term": "Fall 2026",
        "courses": [
            ("ITSC 3160", "Database Design and Implementation", 3),
            ("STAT 2122", "Introduction to Statistics II", 3),
        ],
    },
    {
        "term": "Spring 2027",
        "courses": [
            ("ITSC 3146", "Intro to Operating Systems and Networking", 3),
            ("COMM 2100", "Introduction to Communication Theory", 3),
        ],
    },
    {
        "term": "Summer 2027",
        "courses": [
            ("ITSC 3688", "Computers and Their Impact on Society", 3),
        ],
    },
    {
        "term": "Fall 2027",
        "courses": [
            ("ITSC 4850", "Senior Project", 3),
            ("STAT 3110", "Applied Regression", 3),
        ],
    },
]

SKILL_GAPS = [
    {
        "skill": "SQL",
        "current": "Intro",
        "target": "Proficient",
        "course": "ITSC 3160",
    },
    {
        "skill": "Statistics",
        "current": "Introductory",
        "target": "Intermediate",
        "course": "STAT 2122",
    },
    {
        "skill": "Communication",
        "current": "Developing",
        "target": "Proficient",
        "course": "COMM 2100",
    },
]

# (from_column, from_row, to_column, to_row)
# Columns: 0 current courses, 1 courses needed, 2 career.
SKILL_LINKS = [
    (0, 0, 1, 0),
    (0, 1, 1, 1),
    (0, 2, 1, 2),
    (1, 0, 2, 0),
    (1, 1, 2, 0),
    (1, 2, 2, 0),
]


def _audit_summary(audit: dict) -> str:
    return (
        f"{audit['major']} ({audit['catalog_year']}): "
        f"{audit['credits_applied']} of {audit['credits_required']} credits applied. "
        f"{len(audit['courses_completed'])} completed, "
        f"{len(audit['courses_in_progress'])} in progress, "
        f"{len(audit['courses_preregistered'])} preregistered, "
        f"{len(audit['courses_not_taken'])} still needed."
    )


def _seed_message(prefs: dict, audit: dict) -> str:
    summer = (
        "Summer 2027 stays in the sequence as a lighter term."
        if prefs["include_summer"]
        else "Summer 2027 is listed as an optional lighter term."
    )
    if prefs["priority"] == "Finish sooner":
        priority = "finishing sooner, with the smaller terms first"
    else:
        priority = "closing skill gaps first: SQL, statistics, then communication"
    return (
        f"Parsed {prefs['filename']}. {_audit_summary(audit)} "
        f"For {_career_label(prefs)}, the sample plan favors "
        f"{priority}. You set a cap of {prefs['credits']} credits per term; the "
        f"cards below are a fixed sample, not a schedule rebuilt to that cap. "
        f"{summer} Fall 2026 starts with ITSC 3160 and STAT 2122. Spring 2027 "
        "adds ITSC 3146 and COMM 2100. Summer 2027 is ITSC 3688. Fall 2027 "
        "finishes with ITSC 4850 and STAT 3110."
    )


def _chat_reply(prefs: dict, prompt: str) -> str:
    session_id = st.session_state.session_id
    if not session_id:
        return "The audit is gone. Upload the DegreeWorks PDF again."
    history = [
        {"role": item["role"], "content": item["content"]}
        for item in st.session_state.messages[:-1]
    ]
    try:
        payload = chat.post_chat(BACKEND_URL, session_id, prompt, history, prefs)
    except chat.ChatFailed as exc:
        if exc.status == 404:
            return "The audit is gone. Upload the DegreeWorks PDF again."
        if str(exc) == "timed out":
            return "The reply timed out."
        return f"The reply could not be generated. {exc}"
    reply = payload.get("reply")
    if not reply:
        return "The reply could not be generated."
    return reply


def _soc_codes(prefs: dict) -> list[str]:
    return [career["soc_code"] for career in prefs.get("careers", [])]


def _load_recommendation(prefs: dict) -> None:
    """Fetch /recommend once per plan; keep the result or a readable error."""
    st.session_state.recommendation = None
    st.session_state.recommend_error = None
    try:
        st.session_state.recommendation = recommend.post_recommend(
            BACKEND_URL, st.session_state.session_id, _soc_codes(prefs), RECOMMEND_LIMIT
        )
    except recommend.BackendFailed as exc:
        if exc.status == 422 and "catalog" in str(exc):
            message = f"Recommendations are unavailable for this audit: {exc}."
        elif exc.status == 404:
            message = "The audit expired. Upload it again."
        elif exc.status == 409:
            message = "Recommendations are unavailable: course data is still loading."
        else:
            message = f"Recommendations are unavailable. {exc}"
        st.session_state.recommend_error = message


def _match_label(score: float, top: float) -> str:
    """Relative label: scores rank courses, they do not measure skill."""
    if top <= 0:
        return "Match"
    ratio = score / top
    if ratio >= 0.85:
        return "Strong match"
    if ratio >= 0.6:
        return "Moderate match"
    return "Weaker match"


def _recommendation_rows() -> list[dict]:
    result = st.session_state.get("recommendation") or {}
    return result.get("recommendations") or []


def _recommendations_section() -> None:
    st.subheader("Recommended courses")
    if st.session_state.get("recommend_error"):
        st.info(st.session_state.recommend_error)
        return
    result = st.session_state.get("recommendation") or {}
    rows = _recommendation_rows()
    if not rows:
        st.caption("No still-needed courses with a named course code were found in this audit.")
        return
    titles = {o["soc_code"]: o["title"] for o in result.get("occupations", [])}
    top = rows[0]["score"]
    for row in rows:
        best = max(row["similarity_by_occupation"], key=row["similarity_by_occupation"].get)
        st.markdown(
            f"**{row['code']}** {row['title']} · {row['credits']} cr  \n"
            f"{_match_label(row['score'], top)} for {titles.get(best, best)}"
            f" · satisfies {', '.join(row['requirement_blocks']) or 'a listed requirement'}"
        )
        unmet = [p["code"] for p in row.get("prerequisites", []) if not p["met"]]
        if unmet:
            st.caption(
                f"Prerequisites not found in your audit: {', '.join(unmet)}. "
                "An alternative course may already satisfy them."
            )
    unmatched = [item["code"] for item in result.get("unmatched", [])]
    if unmatched:
        st.caption(
            f"Not in the {result.get('catalog', 'loaded')} catalog: {', '.join(unmatched)}"
        )


def _recommendation_seed(prefs: dict, audit: dict) -> str:
    """First chat message in explain mode: built from /recommend, no model call."""
    rows = _recommendation_rows()[:3]
    if not rows:
        return f"Parsed {prefs['filename']}. {_audit_summary(audit)}"
    picks = ", ".join(f"{row['code']} {row['title']}" for row in rows)
    return (
        f"Parsed {prefs['filename']}. {_audit_summary(audit)} "
        f"For {_career_label(prefs)}, the closest matches among your remaining "
        f"courses are {picks}. Ask why a course fits, or about any course code."
    )


def _explain_message(prefs: dict, prompt: str) -> dict:
    """Assistant message from /explain, with its cited sources attached."""
    session_id = st.session_state.session_id
    if not session_id:
        return {"role": "assistant", "content": "The audit is gone. Upload the DegreeWorks PDF again."}
    try:
        with st.spinner("Finding the evidence and writing an answer..."):
            payload = recommend.post_explain(BACKEND_URL, session_id, _soc_codes(prefs), prompt)
    except recommend.BackendFailed as exc:
        if exc.status == 404:
            return {"role": "assistant", "content": "The audit is gone. Upload the DegreeWorks PDF again."}
        if exc.status == 503 and exc.body.get("evidence"):
            return {
                "role": "assistant",
                "content": "The language model is unavailable, so here are the facts found for your question.",
                "sources": exc.body["evidence"],
            }
        if str(exc) == "timed out":
            return {"role": "assistant", "content": "The reply timed out."}
        return {"role": "assistant", "content": f"The reply could not be generated. {exc}"}
    evidence = {item["id"]: item for item in payload.get("evidence", [])}
    cited = [evidence[cid] for cid in payload.get("citations", []) if cid in evidence]
    content = payload.get("answer") or "The reply could not be generated."
    if not payload.get("grounded", False):
        content = (
            "This answer could not be checked against its sources, so here are the "
            "facts found for your question instead."
        )
        cited = list(evidence.values())
    return {"role": "assistant", "content": content, "sources": cited}


def _assistant_message(prefs: dict, prompt: str) -> dict:
    if CHAT_MODE == "explain":
        return _explain_message(prefs, prompt)
    return {"role": "assistant", "content": _chat_reply(prefs, prompt)}


def _terms_html() -> str:
    cards = []
    for term in TERMS:
        courses = []
        for code, title, credits in term["courses"]:
            courses.append(
                "<p class='term-course'>"
                f"<strong>{html.escape(code)}</strong>"
                f"<span>{html.escape(title)} · {credits} cr</span>"
                "</p>"
            )
        cards.append(
            "<article class='term-card'>"
            f"<h4>{html.escape(term['term'])}</h4>"
            f"{''.join(courses)}"
            "</article>"
        )
    return f"<div class='cw-terms'>{''.join(cards)}</div>"


def _gaps_html() -> str:
    rows = []
    for gap in SKILL_GAPS:
        rows.append(
            "<div class='gap-row'>"
            f"<div><span class='label'>Skill</span>{html.escape(gap['skill'])}</div>"
            "<div><span class='label'>Level</span>"
            f"{html.escape(gap['current'])} → {html.escape(gap['target'])}</div>"
            "<div><span class='label'>Course</span>"
            f"{html.escape(gap['course'])}</div>"
            "</div>"
        )
    return f"<div class='gap-list'>{''.join(rows)}</div>"


def _node_center(column: int, row: int) -> tuple[float, float]:
    x = 36 + column * 230 + 90
    if column == 2:
        y = 150
    else:
        y = 78 + row * 72
    return x, y


def _career_label(prefs: dict) -> str:
    titles = [career["title"] for career in prefs["careers"]]
    if len(titles) == 1:
        return titles[0]
    if len(titles) == 2:
        return f"{titles[0]} and {titles[1]}"
    return ", ".join(titles[:-1]) + f", and {titles[-1]}"


def _wrap_title(title: str, width: int = 22) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in title.split():
        trial = word if not current else f"{current} {word}"
        if len(trial) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _graph_data(audit: dict | None) -> tuple[list[str], list[str], list[tuple[int, int, int, int]]]:
    """Graph columns from real data when /recommend succeeded, else the sample.

    Current: up to 3 completed or in-progress courses. Needed: the top 3
    recommendations. A current->needed link is drawn only where the catalog
    lists the current course as a prerequisite of the needed one; every
    needed course links to the career column.
    """
    rows = _recommendation_rows()[:3]
    if not rows or not audit:
        return CURRENT_COURSES, NEEDED_COURSES, SKILL_LINKS
    needed = [row["code"] for row in rows]
    taken = [
        course["code"]
        for key in ("courses_in_progress", "courses_completed")
        for course in audit.get(key) or []
    ]
    prereq_codes = {p["code"] for row in rows for p in row.get("prerequisites", [])}
    current = [code for code in taken if code in prereq_codes][:3]
    current += [code for code in taken if code not in current][: 3 - len(current)]
    links = []
    for n_row, row in enumerate(rows):
        for c_row, code in enumerate(current):
            if any(p["code"] == code for p in row.get("prerequisites", [])):
                links.append((0, c_row, 1, n_row))
        links.append((1, n_row, 2, 0))
    return current, needed, links


def _graph_html(
    careers: list[dict],
    current: list[str] | None = None,
    needed: list[str] | None = None,
    skill_links: list[tuple[int, int, int, int]] | None = None,
) -> str:
    current = CURRENT_COURSES if current is None else current
    needed = NEEDED_COURSES if needed is None else needed
    skill_links = SKILL_LINKS if skill_links is None else skill_links
    headings = [
        (36, "Current courses"),
        (266, "Courses needed"),
        (496, "Career"),
    ]
    heading_svg = "".join(
        f"<text class='heading' x='{x}' y='28'>{html.escape(label)}</text>"
        for x, label in headings
    )

    columns = [current, needed]
    kinds = ["current", "needed"]
    nodes = []
    for column, (labels, kind) in enumerate(zip(columns, kinds)):
        for row, label in enumerate(labels):
            x, y = _node_center(column, row)
            left = x - 90
            top = y - 18
            nodes.append(
                f"<g class='node {kind}'>"
                f"<rect x='{left}' y='{top}' width='180' height='36' rx='8'/>"
                f"<text x='{left + 10}' y='{top + 23}'>{html.escape(label)}</text>"
                "</g>"
            )
    career_lines: list[str] = []
    for career in careers:
        career_lines.extend(_wrap_title(career["title"]))
    if not career_lines:
        career_lines = ["Career"]
    career_height = max(36, 12 + len(career_lines) * 16)
    career_x, career_y = _node_center(2, 0)
    career_left = career_x - 90
    career_top = career_y - career_height / 2
    tspans = []
    for index, line in enumerate(career_lines):
        dy = 0 if index == 0 else 16
        tspans.append(
            f"<tspan x='{career_left + 10}' dy='{dy}'>{html.escape(line)}</tspan>"
        )
    first_baseline = career_top + 20
    nodes.append(
        "<g class='node career'>"
        f"<rect x='{career_left}' y='{career_top}' width='180' height='{career_height}' rx='8'/>"
        f"<text x='{career_left + 10}' y='{first_baseline}'>{''.join(tspans)}</text>"
        "</g>"
    )

    links = []
    for start_col, start_row, end_col, end_row in skill_links:
        x1, y1 = _node_center(start_col, start_row)
        x2, y2 = _node_center(end_col, end_row)
        links.append(
            f"<line class='link' x1='{x1 + 90}' y1='{y1}' x2='{x2 - 90}' y2='{y2}'/>"
        )

    return (
        "<svg class='skill-graph' viewBox='0 0 700 280' role='img' "
        "aria-label='Skill links among current courses, needed courses, and career'>"
        f"{''.join(links)}{heading_svg}{''.join(nodes)}</svg>"
    )


@st.cache_data(show_spinner=False)
def _syllab_map_courses() -> list[str]:
    return sorted(
        {
            path.parent.name
            for path in SYLLAB_MAP_DIR.glob("*/*_graph.png")
            if path.is_file()
        }
    )


def _syllab_map_graph() -> None:
    st.subheader("SyllabCMap course concept map")
    courses = _syllab_map_courses()
    if not courses:
        st.info("No SyllabCMap graph images were found.")
        return

    preferred = [
        row.get("code", "")
        for row in _recommendation_rows()
        if isinstance(row.get("code"), str)
    ]
    audit = st.session_state.get("audit") or {}
    preferred.extend(
        course.get("code", "")
        for status in ("courses_in_progress", "courses_completed", "courses_not_taken")
        for course in audit.get(status) or []
        if isinstance(course.get("code"), str)
    )
    default = next(
        (
            code.strip().upper().replace(" ", "_")
            for code in preferred
            if code.strip().upper().replace(" ", "_") in courses
        ),
        "ITSC_3160" if "ITSC_3160" in courses else courses[0],
    )
    selected = st.selectbox(
        "Course map",
        courses,
        index=courses.index(default),
        format_func=lambda code: code.replace("_", " "),
        key="syllab_map_course",
        help="Search course maps generated from syllabCMap.",
    )
    image_path = SYLLAB_MAP_DIR / selected / f"{selected}_graph.png"
    st.image(
        str(image_path),
        caption="Syllabus concept map; dashed outlines indicate inferred concepts.",
        width="stretch",
        alt=f"Syllabus concept map for {selected.replace('_', ' ')}",
    )


def _show_html(fragment: str) -> None:
    if hasattr(st, "html"):
        st.html(fragment)
    else:
        st.markdown(fragment, unsafe_allow_html=True)


def _init_state() -> None:
    if "theme_mode" not in st.session_state:
        st.session_state.theme_mode = "Light"
    if "plan_ready" not in st.session_state:
        st.session_state.plan_ready = False
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "prefs" not in st.session_state:
        st.session_state.prefs = None
    if "selected_careers" not in st.session_state:
        st.session_state.selected_careers = {}
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "audit" not in st.session_state:
        st.session_state.audit = None
    if "recommendation" not in st.session_state:
        st.session_state.recommendation = None
    if "recommend_error" not in st.session_state:
        st.session_state.recommend_error = None


@st.cache_data(ttl=300, show_spinner=False)
def _load_occupations() -> dict:
    with urllib.request.urlopen(f"{BACKEND_URL}/occupations", timeout=5) as response:
        return json.load(response)


def _career_menu() -> list[dict]:
    try:
        payload = _load_occupations()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        st.error("Occupations are unavailable.")
        return []
    chosen: dict[str, str] = {}
    with st.container(height="content", gap=2, key="occ_menu"):
        for category in payload.get("categories", []):
            occupations = category["occupations"]
            label = f"{category['name']} ({len(occupations)})"
            with st.expander(label):
                for occupation in occupations:
                    soc = occupation["soc_code"]
                    title = occupation["title"]
                    checked = st.checkbox(title, key=f"occ_{soc}")
                    if checked:
                        chosen[soc] = title
    st.session_state.selected_careers = chosen
    count = len(chosen)
    noun = "career" if count == 1 else "careers"
    st.caption(f"{count} {noun} selected")
    return [{"soc_code": soc, "title": title} for soc, title in chosen.items()]


@st.fragment(run_every=20)
def _keep_audit() -> None:
    """Renew the short safety TTL while this page is still connected."""
    if st.session_state.get("session_id"):
        watch_session(BACKEND_URL, st.session_state.session_id)
        _refresh_audit()


def _refresh_audit() -> None:
    """Renew the audit while this page is open. A missing key clears it."""
    session_id = st.session_state.session_id
    if not session_id:
        return
    watch_session(BACKEND_URL, session_id)
    try:
        payload = load_audit(BACKEND_URL, session_id)
    except AuditUnavailable:
        st.warning("The saved audit could not be refreshed.")
        return
    if payload is None:
        st.session_state.session_id = None
        st.session_state.audit = None
        st.session_state.plan_ready = False
        st.session_state.prefs = None
        st.session_state.messages = []
        st.session_state.recommendation = None
        st.session_state.recommend_error = None
        st.warning("This audit expired. Upload it again.")
        return
    st.session_state.audit = payload["audit"]


def _store_upload(
    uploaded,
    careers: list[dict],
    credits: int,
    include_summer: bool,
    priority: str,
) -> None:
    try:
        payload = post_audit(
            BACKEND_URL,
            uploaded.getvalue(),
            uploaded.name,
            st.session_state.session_id,
        )
    except AuditUnavailable as exc:
        if exc.status == 422:
            st.error("That PDF could not be read as a DegreeWorks audit.")
        else:
            st.error("The audit could not be saved.")
        return
    st.session_state.session_id = payload["session_id"]
    st.session_state.audit = payload["audit"]
    watch_session(BACKEND_URL, payload["session_id"])
    st.session_state.plan_ready = True
    st.session_state.prefs = {
        "filename": uploaded.name,
        "careers": careers,
        "credits": credits,
        "include_summer": include_summer,
        "priority": priority,
    }
    _load_recommendation(st.session_state.prefs)
    st.session_state.messages = []
    if CHAT_MODE == "explain":
        # No model call on upload: the first message comes from /recommend.
        reply = _recommendation_seed(st.session_state.prefs, payload["audit"])
    else:
        seed = _seed_message(st.session_state.prefs, payload["audit"])
        reply = _chat_reply(
            st.session_state.prefs,
            "Write the first recommendation from this parsed-audit draft. "
            "Do not copy the draft verbatim.\n\n" + seed,
        )
    st.session_state.messages = [{"role": "assistant", "content": reply}]


def _preferences() -> None:
    st.subheader("Build your plan")
    with st.container(border=True):
        st.markdown("#### 1 · Upload your audit")
        uploaded = st.file_uploader(
            "DegreeWorks audit",
            type=["pdf"],
            help="Kept for this page only. A refresh discards the parsed audit.",
        )
        st.divider()
        st.markdown("#### 2 · Choose target careers")
        careers = _career_menu()
        st.divider()
        st.markdown("#### 3 · Set your preferences")
        credit_col, summer_col = st.columns(2)
        credits = credit_col.slider(
            "Credits per semester", min_value=3, max_value=18, value=15
        )
        include_summer = summer_col.checkbox("Include summer terms", value=True)
        priority = st.radio(
            "Priority",
            ["Finish sooner", "Close skill gaps"],
            horizontal=True,
        )
        if st.button("Build plan", type="primary"):
            if uploaded is None:
                st.warning("Upload the DegreeWorks audit first.")
                return
            if not careers:
                st.warning("Select at least one career.")
                return
            _store_upload(uploaded, careers, credits, include_summer, priority)
    if st.session_state.audit:
        with st.container(border=True):
            st.markdown("#### Audit summary")
            st.info(_audit_summary(st.session_state.audit))


def _chat(prefs: dict) -> None:
    st.subheader("Plan assistant")
    with st.container(height=280):
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message.get("sources"):
                    with st.expander(f"Sources ({len(message['sources'])})"):
                        for source in message["sources"]:
                            st.markdown(f"**[{source['id']}]** {source['text']}")
    prompt = st.chat_input("Ask about this plan")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.messages.append(_assistant_message(prefs, prompt))
        st.rerun()


def _results() -> None:
    prefs = st.session_state.prefs
    st.subheader("Your plan")
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            _chat(prefs)
        with st.container(border=True):
            st.subheader("Skill gaps")
            st.caption("Sample data: not yet computed from your audit.")
            _show_html(_gaps_html())
        with st.container(border=True):
            st.subheader("Semester sequence")
            st.caption("Sample sequence; not yet generated from your audit.")
            _show_html(_terms_html())
    with right:
        with st.container(border=True):
            _recommendations_section()
        with st.container(border=True):
            st.subheader("Skill links")
            current, needed, links = _graph_data(st.session_state.audit)
            _show_html(_graph_html(prefs["careers"], current, needed, links))
    with st.container(border=True):
        _syllab_map_graph()


def main() -> None:
    st.set_page_config(
        page_title="ClassWizard",
        page_icon=str(LOGO_PATH),
        layout="wide",
    )
    _init_state()
    style.apply(st.session_state.theme_mode)
    logo_column, title_column, theme_column = st.columns([1, 6, 2])
    with logo_column:
        st.image(str(LOGO_PATH), width=82)
    with title_column:
        st.title("ClassWizard")
        st.caption("Career-aware course planning")
    with theme_column:
        st.selectbox("Appearance", ["Light", "Dark"], key="theme_mode")
    st.caption("Semester sequence and skill-gap panels currently use sample data.")
    _keep_audit()
    _refresh_audit()
    _preferences()
    if st.session_state.plan_ready:
        _results()


main()
