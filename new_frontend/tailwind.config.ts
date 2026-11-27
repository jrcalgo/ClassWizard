import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

// Colours are CSS variables (src/index.css) holding "R G B" triples, ported
// from the Streamlit palettes in frontend/src/style.py.
const token = (name: string) => `rgb(var(--cw-${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Avenir Next"', '"Segoe UI"', "system-ui", "sans-serif"],
      },
      colors: {
        bg: token("bg"),
        card: token("card"),
        "card-alt": token("card-alt"),
        text: token("text"),
        muted: token("muted"),
        border: token("border"),
        green: token("green"),
        "green-hover": token("green-hover"),
        "on-green": token("on-green"),
        button: token("button"),
        "button-hover": token("button-hover"),
        "on-button": token("on-button"),
        selection: token("selection-bg"),
        "on-selection": token("selection-text"),
        gold: token("gold"),
        link: token("link"),
        danger: token("danger"),
      },
      borderRadius: {
        card: "16px",
        zone: "12px",
        btn: "10px",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
      },
      animation: { "fade-in": "fade-in 150ms ease-out" },
    },
  },
  plugins: [animate],
} satisfies Config;
