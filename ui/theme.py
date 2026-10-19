"""Theme tokens, custom CSS styles, and subtle motion transitions for AMOLED workspace."""

import streamlit as st

# AMOLED Design Tokens
COLOR_BG = "#050608"
COLOR_SURFACE = "#0C0D12"
COLOR_ELEVATED = "#14151D"
COLOR_BORDER = "#252632"
COLOR_PRIMARY = "#B9A3FF"
COLOR_SECONDARY = "#70D9C2"
COLOR_TEXT_PRIMARY = "#F5F3FF"
COLOR_TEXT_MUTED = "#9693A6"
COLOR_DANGER = "#FF7B72"
COLOR_WARNING = "#F0883E"

THEME_CSS = f"""
<style>
/* Base AMOLED Dark Backgrounds */
.stApp {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT_PRIMARY};
}}

[data-testid="stSidebar"] {{
    background-color: {COLOR_SURFACE};
    border-right: 1px solid {COLOR_BORDER};
}}

/* Typography */
h1, h2, h3, h4, h5, h6 {{
    color: {COLOR_TEXT_PRIMARY} !important;
    font-weight: 600;
    letter-spacing: -0.02em;
}}

p, span, label, div {{
    color: {COLOR_TEXT_PRIMARY};
}}

small, .text-muted {{
    color: {COLOR_TEXT_MUTED} !important;
}}

/* Custom Workspace Cards */
.amoled-card {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    padding: 1.25rem;
    margin-bottom: 1rem;
    transition: border-color 180ms ease, transform 180ms ease;
    animation: fadeInUp 200ms cubic-bezier(0.16, 1, 0.3, 1);
}}

.amoled-card:hover {{
    border-color: {COLOR_PRIMARY}80;
    transform: translateY(-1px);
}}

.amoled-card-elevated {{
    background-color: {COLOR_ELEVATED};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 0.75rem;
}}

/* Stat Badge */
.stat-value {{
    font-size: 2rem;
    font-weight: 700;
    color: {COLOR_PRIMARY};
    line-height: 1.1;
    margin-top: 0.25rem;
}}

.stat-label {{
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: {COLOR_TEXT_MUTED};
    font-weight: 600;
}}

.stat-subtext {{
    font-size: 0.8rem;
    color: {COLOR_TEXT_MUTED};
    margin-top: 0.25rem;
}}

/* Status Badges */
.status-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.2rem 0.6rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    line-height: 1;
}}

.status-badge.local {{
    background-color: {COLOR_SECONDARY}1A;
    color: {COLOR_SECONDARY};
    border: 1px solid {COLOR_SECONDARY}40;
}}

.status-badge.cloud {{
    background-color: {COLOR_PRIMARY}1A;
    color: {COLOR_PRIMARY};
    border: 1px solid {COLOR_PRIMARY}40;
}}

.status-badge.warning {{
    background-color: {COLOR_WARNING}1A;
    color: {COLOR_WARNING};
    border: 1px solid {COLOR_WARNING}40;
}}

.status-badge.error {{
    background-color: {COLOR_DANGER}1A;
    color: {COLOR_DANGER};
    border: 1px solid {COLOR_DANGER}40;
}}

/* Buttons */
.stButton > button {{
    background-color: {COLOR_ELEVATED};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    font-weight: 500;
    transition: background-color 150ms ease, border-color 150ms ease;
}}

.stButton > button:hover {{
    background-color: {COLOR_BORDER};
    border-color: {COLOR_PRIMARY};
    color: {COLOR_PRIMARY};
}}

.stButton > button[kind="primary"] {{
    background-color: {COLOR_PRIMARY};
    color: #0A0A0F;
    border: 1px solid {COLOR_PRIMARY};
    font-weight: 600;
}}

.stButton > button[kind="primary"]:hover {{
    background-color: #A489FF;
    border-color: #A489FF;
    color: #000000;
}}

/* Subtle Motion */
@keyframes fadeInUp {{
    from {{
        opacity: 0;
        transform: translateY(6px);
    }}
    to {{
        opacity: 1;
        transform: translateY(0);
    }}
}}

/* Reduced Motion Override */
@media (prefers-reduced-motion: reduce) {{
    *, .amoled-card, .stButton > button {{
        animation: none !important;
        transition: none !important;
        transform: none !important;
    }}
}}

/* Cleaner Streamlit chrome */
#MainMenu, footer, header {{
    visibility: hidden;
}}
</style>
"""


def inject_custom_theme() -> None:
    """Inject AMOLED dark theme custom styling and CSS variables."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)
