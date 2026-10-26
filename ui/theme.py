"""Theme tokens, custom CSS styles, and subtle motion transitions for AMOLED workspace."""

import streamlit as st

# AMOLED Design Tokens (Stage 6 Contract)
COLOR_BG = "#09090B"
COLOR_SURFACE = "#111114"
COLOR_ELEVATED = "#18181D"
COLOR_BORDER = "#29292F"
COLOR_PRIMARY = "#A78BFA"
COLOR_SECONDARY = "#5EEAD4"
COLOR_TEXT_PRIMARY = "#F4F4F5"
COLOR_TEXT_MUTED = "#A1A1AA"
COLOR_DANGER = "#F87171"
COLOR_WARNING = "#FBBF24"

THEME_CSS = f"""
<style>
/* Base AMOLED Dark Backgrounds */
.stApp {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT_PRIMARY};
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}

/* Main Chat Content Column - Centered 820px max width */
.block-container {{
    max-width: 820px !important;
    padding-top: 1.75rem !important;
    padding-bottom: 6rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}}

[data-testid="stSidebar"] {{
    background-color: {COLOR_SURFACE};
    border-right: 1px solid {COLOR_BORDER};
}}

[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{
    display: none;
}}

/* Typography */
h1, h2, h3, h4, h5, h6 {{
    color: {COLOR_TEXT_PRIMARY} !important;
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.3;
}}

p, span, label, div {{
    color: {COLOR_TEXT_PRIMARY};
    font-size: 0.95rem;
    line-height: 1.6;
}}

small, .text-muted {{
    color: {COLOR_TEXT_MUTED} !important;
    font-size: 0.8125rem;
}}

/* Clean Chat Message Styling (ChatGPT / Claude style) */
[data-testid="stChatMessage"] {{
    background-color: transparent !important;
    border: none !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    margin-bottom: 1.5rem !important;
}}

/* User chat message bubble - compact elevated container */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
    background-color: {COLOR_ELEVATED} !important;
    border: 1px solid {COLOR_BORDER} !important;
    border-radius: 12px !important;
    padding: 0.75rem 1rem !important;
    margin-left: auto !important;
    max-width: 85% !important;
}}

/* Assistant chat message - readable uncluttered flow */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {{
    background-color: transparent !important;
    border: none !important;
    padding: 0 !important;
}}

/* Pinned Chat Input at bottom */
[data-testid="stChatInput"] {{
    background-color: {COLOR_SURFACE} !important;
    border: 1px solid {COLOR_BORDER} !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4) !important;
    transition: border-color 150ms ease;
}}

[data-testid="stChatInput"]:focus-within {{
    border-color: {COLOR_PRIMARY} !important;
}}

[data-testid="stChatInput"] textarea {{
    color: {COLOR_TEXT_PRIMARY} !important;
    font-size: 0.95rem !important;
}}

/* Custom Workspace Cards */
.amoled-card {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    padding: 1.25rem;
    margin-bottom: 1rem;
    transition: border-color 180ms ease;
}}

.amoled-card:hover {{
    border-color: {COLOR_BORDER};
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
    font-size: 1.85rem;
    font-weight: 700;
    color: {COLOR_PRIMARY};
    line-height: 1.1;
    margin-top: 0.25rem;
}}

.stat-label {{
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
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
    padding: 0.2rem 0.55rem;
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
    border-radius: 8px;
    font-weight: 500;
    font-size: 0.875rem;
    padding: 0.45rem 0.85rem;
    transition: background-color 150ms ease, border-color 150ms ease;
}}

.stButton > button:hover {{
    background-color: {COLOR_BORDER};
    border-color: {COLOR_PRIMARY}80;
    color: {COLOR_TEXT_PRIMARY};
}}

.stButton > button[kind="primary"] {{
    background-color: {COLOR_PRIMARY};
    color: #09090B;
    border: 1px solid {COLOR_PRIMARY};
    font-weight: 600;
}}

.stButton > button[kind="primary"]:hover {{
    background-color: #906ffa;
    border-color: #906ffa;
    color: #000000;
}}

/* Sidebar New Chat Button */
.new-chat-btn > button {{
    background-color: {COLOR_PRIMARY}1A !important;
    color: {COLOR_PRIMARY} !important;
    border: 1px solid {COLOR_PRIMARY}40 !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
}}

.new-chat-btn > button:hover {{
    background-color: {COLOR_PRIMARY}2E !important;
    border-color: {COLOR_PRIMARY} !important;
}}

/* Expanders */
[data-testid="stExpander"] {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    margin-bottom: 0.75rem;
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
