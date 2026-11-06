import html
import json
import os
import urllib.error
import urllib.request

import streamlit as st

import style
from uploads.degreeworks import AuditUnavailable, load_audit, post_audit, watch_session

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

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


def _follow_up(prefs: dict) -> str:
    return (
        f"The sample plan for {_career_label(prefs)} is still the one in this draft. "
        f"ITSC 3160 covers the SQL gap, STAT 2122 covers statistics, and "
        f"COMM 2100 covers communication. The semester cards are the sequence "
        f"to follow, with a recorded cap of {prefs['credits']} credits per term."
    )


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


def _graph_html(careers: list[dict]) -> str:
    headings = [
        (36, "Current courses"),
        (266, "Courses needed"),
        (496, "Career"),
    ]
    heading_svg = "".join(
        f"<text class='heading' x='{x}' y='28'>{html.escape(label)}</text>"
        for x, label in headings
    )

    columns = [CURRENT_COURSES, NEEDED_COURSES]
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
    for start_col, start_row, end_col, end_row in SKILL_LINKS:
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


def _show_html(fragment: str) -> None:
    if hasattr(st, "html"):
        st.html(fragment)
    else:
        st.markdown(fragment, unsafe_allow_html=True)


def _init_state() -> None:
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


@st.cache_data(ttl=300, show_spinner=False)
def _load_occupations() -> dict:
    with urllib.request.urlopen(f"{BACKEND_URL}/occupations", timeout=5) as response:
        return json.load(response)


def _career_menu() -> list[dict]:
    st.subheader("Target careers")
    try:
        payload = _load_occupations()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        st.error("Occupations are unavailable.")
        return []
    chosen: dict[str, str] = {}
    with st.container(border=True, height="content", gap=2, key="occ_menu"):
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
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": _seed_message(st.session_state.prefs, payload["audit"]),
        }
    ]


def _preferences() -> None:
    uploaded = st.file_uploader(
        "DegreeWorks audit",
        type=["pdf"],
        help="Kept for this page only. A refresh discards the parsed audit.",
    )
    careers = _career_menu()
    credit_col, summer_col = st.columns(2)
    credits = credit_col.slider("Credits per semester", min_value=3, max_value=18, value=15)
    include_summer = summer_col.checkbox("Include summer terms", value=True)
    priority = st.radio(
        "Priority",
        ["Finish sooner", "Close skill gaps"],
        horizontal=True,
    )
    if st.button("Build plan", type="primary"):
        if uploaded is None:
            st.warning("Upload a DegreeWorks PDF first.")
            return
        if not careers:
            st.warning("Select at least one career.")
            return
        _store_upload(uploaded, careers, credits, include_summer, priority)
    if st.session_state.audit:
        st.info(_audit_summary(st.session_state.audit))


def _chat(prefs: dict) -> None:
    st.subheader("Course recommendations")
    with st.container(height=280):
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])
    prompt = st.chat_input("Ask about this plan")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.messages.append(
            {"role": "assistant", "content": _follow_up(prefs)}
        )
        st.rerun()


def _results() -> None:
    prefs = st.session_state.prefs
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            _chat(prefs)
            st.subheader("Semester sequence")
            _show_html(_terms_html())
    with right:
        with st.container(border=True):
            st.subheader("Skill gaps")
            _show_html(_gaps_html())
            st.subheader("Skill links")
            _show_html(_graph_html(prefs["careers"]))


def main() -> None:
    st.set_page_config(page_title="ClassWizard", layout="wide")
    style.apply()
    _init_state()
    st.title("ClassWizard")
    st.caption("Draft planner. Currently WIP; non-operational.")
    _keep_audit()
    _refresh_audit()
    _preferences()
    if st.session_state.plan_ready:
        _results()


main()
