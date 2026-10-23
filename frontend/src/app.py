import html

import streamlit as st

import style

CAREERS = ["Data Analyst", "Software Developer", "Business Analyst"]

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


def _seed_message(prefs: dict) -> str:
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
        f"Using {prefs['filename']} as the uploaded audit. This draft does not "
        f"parse it yet. For a {prefs['career']} role, the sample plan favors "
        f"{priority}. You set a cap of {prefs['credits']} credits per term; the "
        f"cards below are a fixed sample, not a schedule rebuilt to that cap. "
        f"{summer} Fall 2026 starts with ITSC 3160 and STAT 2122. Spring 2027 "
        "adds ITSC 3146 and COMM 2100. Summer 2027 is ITSC 3688. Fall 2027 "
        "finishes with ITSC 4850 and STAT 3110."
    )


def _follow_up(prefs: dict) -> str:
    return (
        f"The sample plan for {prefs['career']} is still the one in this draft. "
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


def _graph_html(career: str) -> str:
    headings = [
        (36, "Current courses"),
        (266, "Courses needed"),
        (496, "Career"),
    ]
    heading_svg = "".join(
        f"<text class='heading' x='{x}' y='28'>{html.escape(label)}</text>"
        for x, label in headings
    )

    columns = [CURRENT_COURSES, NEEDED_COURSES, [career]]
    kinds = ["current", "needed", "career"]
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


def _preferences() -> None:
    uploaded = st.file_uploader(
        "DegreeWorks audit",
        type=["pdf"],
        help="Stored for this session only. This draft does not parse the file.",
    )
    career_col, credit_col, summer_col = st.columns(3)
    career = career_col.selectbox("Target career", CAREERS)
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
        st.session_state.plan_ready = True
        st.session_state.prefs = {
            "filename": uploaded.name,
            "career": career,
            "credits": credits,
            "include_summer": include_summer,
            "priority": priority,
        }
        st.session_state.messages = [
            {"role": "assistant", "content": _seed_message(st.session_state.prefs)}
        ]


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
            _show_html(_graph_html(prefs["career"]))


def main() -> None:
    st.set_page_config(page_title="ClassWizard", layout="wide")
    style.apply()
    _init_state()
    st.title("ClassWizard")
    st.caption("Draft planner. Recommendations below use sample courses.")
    _preferences()
    if st.session_state.plan_ready:
        _results()


main()
