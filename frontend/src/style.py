import streamlit as st

_CSS = """
<style>
[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 12px;
}

.cw-terms {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.term-card {
  flex: 1 1 140px;
  border: 1px solid #d5ddd8;
  border-radius: 10px;
  padding: 10px 12px;
  background: #f7faf8;
}

.term-card h4 {
  margin: 0 0 8px;
  font-size: 0.95rem;
}

.term-course {
  margin: 0 0 8px;
}

.term-course strong {
  display: block;
}

.term-course span {
  color: #4d5c54;
  font-size: 0.85rem;
}

.gap-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gap-row {
  display: grid;
  grid-template-columns: 1.1fr 1.4fr 1.3fr;
  gap: 8px;
  align-items: start;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f7faf8;
  border: 1px solid #d5ddd8;
}

.gap-row .label {
  display: block;
  font-size: 0.75rem;
  color: #5c6b64;
}

.skill-graph {
  width: 100%;
  height: auto;
}

.skill-graph .link {
  stroke: #8aa394;
  stroke-width: 1.5;
}

.skill-graph .node rect {
  fill: #f7faf8;
  stroke: #1f4d3a;
  stroke-width: 1.5;
}

.skill-graph .node.needed rect {
  stroke: #8a5a12;
}

.skill-graph .node.career rect {
  fill: #1f4d3a;
}

.skill-graph text {
  font-size: 12px;
  fill: #1c2b24;
  font-family: sans-serif;
}

.skill-graph .node.career text {
  fill: #ffffff;
}

.skill-graph .heading {
  font-size: 11px;
  fill: #5c6b64;
}
</style>
"""


def apply() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
