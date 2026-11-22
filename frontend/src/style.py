import streamlit as st

_PALETTES = {
    "Light": {
        "bg": "#f3f6f3",
        "card": "#ffffff",
        "card-alt": "#f7faf8",
        "text": "#17251e",
        "muted": "#52645a",
        "border": "#d5ddd8",
        "green": "#1f4d3a",
        "green-hover": "#53e6a9",
        "on-green": "#ffffff",
        "button": "#1f4d3a",
        "button-hover": "#173d2d",
        "on-button": "#ffffff",
        "selection-border": "transparent",
        "selection-bg": "#1f4d3a",
        "selection-text": "#FFFFFF",
        "gold": "#a66c13",
        "link": "#1b6546",
    },
    "Dark": {
        "bg": "#101814",
        "card": "#17231d",
        "card-alt": "#1d2b24",
        "text": "#edf4ee",
        "muted": "#b6c4ba",
        "border": "#34443a",
        "green": "#75b88b",
        "green-hover": "#91cba3",
        "on-green": "#102017",
        "button": "#286b45",
        "button-hover": "#215936",
        "on-button": "#ffffff",
        "selection-border": "#286b45",
        "selection-bg": "#286b45",
        "selection-text": "#FFFFFF",
        "gold": "#f0c66f",
        "link": "#a5d9b5",
    },
}

_CSS = """
<style>
:root {
  --primary-color: {green};
  --cw-bg: {bg};
  --cw-card: {card};
  --cw-card-alt: {card-alt};
  --cw-text: {text};
  --cw-muted: {muted};
  --cw-border: {border};
  --cw-green: {green};
  --cw-green-hover: {green-hover};
  --cw-on-green: {on-green};
  --cw-button: {button};
  --cw-button-hover: {button-hover};
  --cw-on-button: {on-button};
  --cw-selection-border: {selection-border};
  --cw-selection-bg: {selection-bg};
  --cw-selection-text: {selection-text};
  --cw-gold: {gold};
  --cw-link: {link};
  --cw-body-font: "Avenir Next", "Segoe UI", sans-serif;
}

html, body, .stApp, [data-testid="stAppViewContainer"] {
  background: var(--cw-bg);
  color: var(--cw-text);
  font-family: var(--cw-body-font);
}

[data-testid="stHeader"] {
  background: var(--cw-bg);
}

[data-testid="stMainBlockContainer"] {
  max-width: 1320px;
  padding-top: 2rem;
  padding-bottom: 3rem;
}

.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
  color: var(--cw-text) !important;
  font-family: var(--cw-body-font) !important;
  letter-spacing: -0.02em;
}

::selection,
*::selection {
  background: var(--cw-selection-bg) !important;
  color: #ffffff !important;
}

::-moz-selection,
*::-moz-selection {
  background: var(--cw-selection-bg) !important;
  color: #ffffff !important;
}

[data-testid="stAppViewContainer"] input,
[data-testid="stAppViewContainer"] textarea,
[data-testid="stAppViewContainer"] button,
[data-testid="stMarkdownContainer"] p,
[data-testid="stWidgetLabel"] p,
[data-testid="stCaptionContainer"] {
  color: var(--cw-muted);
  font-family: var(--cw-body-font) !important;
}

input[type="checkbox"],
input[type="radio"] {
  accent-color: var(--cw-green) !important;
}

.react-aria-ComboBox [role="group"]:focus-within {
  border-color: var(--cw-green) !important;
  box-shadow: 0 0 0 1px var(--cw-green) !important;
}

[data-testid="stCheckbox"] label > div {
  border-color: var(--cw-border) !important;
}

[data-testid="stCheckbox"][data-selected="true"] label > div {
  border-color: var(--cw-green) !important;
  background: var(--cw-green) !important;
}

[data-testid="stCheckbox"][data-selected="true"] label > div polyline {
  stroke: var(--cw-on-green) !important;
}

[data-testid="stCheckbox"] label[data-selected="true"] {
  border-radius: 0.5rem;
  background: var(--cw-selection-bg);
}

[data-testid="stCheckbox"] label[data-selected="true"] p {
  color: var(--cw-selection-text) !important;
}

[data-testid="stCheckbox"] label[data-selected="true"]:has(input[aria-label="Include summer terms"]) {
  gap: 0.6rem;
  padding: 0.55rem 0.85rem;
  border: 1px solid var(--cw-selection-border);
  border-radius: 0.75rem;
  background: var(--cw-selection-bg);
}

[data-testid="stCheckbox"] label[data-selected="true"]:has(input[aria-label="Include summer terms"]) [data-testid="stMarkdownContainer"] p {
  color: var(--cw-selection-text) !important;
}

[data-testid="stRadioOption"] > div > div:first-child {
  border-color: var(--cw-border) !important;
}

[data-testid="stRadioOption"][data-selected="true"] > div > div:first-child {
  border-color: var(--cw-green) !important;
  background: var(--cw-green) !important;
}

[data-testid="stRadioOption"][data-selected="true"] {
  border-radius: 0.5rem;
  background: var(--cw-selection-bg);
}

[data-testid="stRadioOption"][data-selected="true"] p {
  color: var(--cw-selection-text) !important;
}

[data-testid="stSlider"] [data-rac][data-orientation="horizontal"],
[data-testid="stSlider"] [data-rac][data-orientation="horizontal"] > div[data-rac] {
  background: transparent !important;
}

[data-testid="stVerticalBlockBorderWrapper"] {
  border: 1px solid var(--cw-border);
  border-radius: 16px;
  background: var(--cw-card);
}

[data-testid="stFileUploaderDropzone"] {
  border: 1px dashed var(--cw-border);
  border-radius: 12px;
  background: var(--cw-card-alt);
}

[data-baseweb="select"] > div,
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
  border-color: var(--cw-border);
  background: var(--cw-card-alt);
  color: var(--cw-text);
}

[data-testid="stExpander"] {
  border-color: var(--cw-border);
  background: var(--cw-card-alt);
}

.stButton > button {
  border-radius: 10px;
  border-color: var(--cw-border);
  color: var(--cw-text);
  font-family: var(--cw-body-font);
  font-weight: 600;
  transition: background-color 120ms ease, border-color 120ms ease;
}

.stButton > button:hover {
  border-color: var(--cw-green);
  color: var(--cw-green);
}

.stButton > button[kind="primary"],
[data-testid="stBaseButton-primary"] {
  border-color: var(--cw-button) !important;
  background: var(--cw-button) !important;
  color: #ffffff !important;
}

.stButton > button[kind="primary"]:hover,
[data-testid="stBaseButton-primary"]:hover {
  border-color: var(--cw-button-hover) !important;
  background: var(--cw-button-hover) !important;
  color: #ffffff !important;
}

.stButton > button[kind="primary"] p,
[data-testid="stBaseButton-primary"] p {
  color: #ffffff !important;
  font-weight: 700 !important;
}

.cw-terms {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.term-card {
  min-width: 0;
  border: 1px solid var(--cw-border);
  border-radius: 12px;
  padding: 10px;
  background: var(--cw-card-alt);
}

.term-card h4 {
  margin: 0 0 10px;
  font-size: 1rem;
}

.term-course {
  margin: 0 0 10px;
}

.term-course strong {
  display: block;
  color: var(--cw-green);
}

.term-course span {
  color: var(--cw-muted);
  font-size: 0.88rem;
}

.gap-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.gap-row {
  display: grid;
  grid-template-columns: 1.1fr 1.4fr 1.3fr;
  gap: 12px;
  align-items: start;
  padding: 12px;
  border-radius: 10px;
  background: var(--cw-card-alt);
  border: 1px solid var(--cw-border);
}

.gap-row .label {
  display: block;
  font-size: 0.75rem;
  color: var(--cw-muted);
}

.skill-graph {
  width: 100%;
  height: auto;
}

.skill-graph .link {
  stroke: var(--cw-muted);
  stroke-width: 1.5;
}

.skill-graph .node rect {
  fill: var(--cw-card-alt);
  stroke: var(--cw-green);
  stroke-width: 1.5;
}

.skill-graph .node.needed rect {
  stroke: var(--cw-gold);
}

.skill-graph .node.career rect {
  fill: var(--cw-green);
}

.skill-graph text {
  font-size: 12px;
  fill: var(--cw-text);
  font-family: var(--cw-body-font);
}

.skill-graph .node.career text {
  fill: var(--cw-on-green);
}

.skill-graph .heading {
  font-size: 11px;
  fill: var(--cw-muted);
}

.st-key-occ_menu,
.st-key-occ_menu [data-testid="stVerticalBlockBorderWrapper"] {
  height: auto !important;
  max-height: none !important;
  overflow: visible !important;
  padding-top: 0.45rem;
  padding-bottom: 0.45rem;
}

.st-key-occ_menu [data-testid="stElementContainer"] {
  margin: 0;
  padding: 0;
}

.st-key-occ_menu div[data-testid="stExpander"] {
  margin: 0;
  border: none;
}

div[data-testid="stExpander"] details summary {
  min-height: 0;
  padding: 0.2rem 0.45rem;
}

div[data-testid="stExpander"] details summary p {
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.3;
}

div[data-testid="stExpanderDetails"] {
  padding: 0 0.45rem 0.25rem;
}

div[data-testid="stExpander"] [data-testid="stVerticalBlock"] {
  gap: 0;
}

div[data-testid="stExpander"] [data-testid="stElementContainer"] {
  margin-bottom: 0;
  padding-top: 0;
  padding-bottom: 0;
}

div[data-testid="stExpander"] [data-testid="stCheckbox"] {
  min-height: 0;
}

div[data-testid="stExpander"] [data-testid="stCheckbox"] label {
  min-height: 0;
  padding: 0.08rem 0;
}

div[data-testid="stExpander"] [data-testid="stCheckbox"] label p {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.3;
}

@media (max-width: 768px) {
  [data-testid="stMainBlockContainer"] {
    padding: 1rem 1rem 2rem;
  }

  .gap-row {
    grid-template-columns: 1fr;
  }

  .cw-terms {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
"""


def apply(mode: str = "Light") -> None:
    if mode not in _PALETTES:
        raise ValueError(f"Unknown color theme: {mode}")
    css = _CSS
    for key, value in _PALETTES[mode].items():
        css = css.replace(f"{{{key}}}", value)
    st.markdown(css, unsafe_allow_html=True)
