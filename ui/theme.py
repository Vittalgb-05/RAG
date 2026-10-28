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
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}}

/* Main Chat Content Column - Centered 820px max width */
.block-container {{
    max-width: 820px !important;
    padding-top: 1.5rem !important;
    padding-bottom: 6rem !important;
    padding-left: 1.25rem !important;
    padding-right: 1.25rem !important;
}}

[data-testid="stSidebar"] {{
    background-color: {COLOR_SURFACE};
    border-right: 1px solid {COLOR_BORDER};
}}

[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{
    display: none;
}}

/* Clean Sidebar Navigation - Transform Radio into Sleek Workspace Tabs */
[data-testid="stSidebar"] [data-testid="stRadio"] > div {{
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
}}

[data-testid="stSidebar"] [data-testid="stRadio"] label {{
    display: flex;
    align-items: center;
    padding: 0.45rem 0.75rem;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 140ms ease, color 140ms ease;
    font-size: 0.85rem;
    font-weight: 500;
    color: {COLOR_TEXT_MUTED};
    margin: 0 !important;
}}

[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {{
    background-color: {COLOR_ELEVATED};
    color: {COLOR_TEXT_PRIMARY};
}}

[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {{
    background-color: {COLOR_ELEVATED};
    border: 1px solid {COLOR_BORDER};
    color: #FFFFFF;
    font-weight: 600;
}}

[data-testid="stSidebar"] [data-testid="stRadio"] input[type="radio"] {{
    display: none;
}}

[data-testid="stSidebar"] [data-testid="stRadio"] > label {{
    display: none; /* Hide 'Navigation' text label */
}}

/* Typography */
h1, h2, h3, h4, h5, h6 {{
    color: {COLOR_TEXT_PRIMARY} !important;
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.35;
}}

p, span, label, div {{
    color: {COLOR_TEXT_PRIMARY};
    font-size: 0.95rem;
    line-height: 1.65;
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
    margin-bottom: 1.25rem !important;
}}

/* User chat message bubble - compact elevated container */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
    background-color: {COLOR_ELEVATED} !important;
    border: 1px solid {COLOR_BORDER} !important;
    border-radius: 16px !important;
    padding: 0.75rem 1.15rem !important;
    margin-left: auto !important;
    max-width: 85% !important;
}}

/* Assistant chat message - readable uncluttered flow */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {{
    background-color: transparent !important;
    border: none !important;
    padding: 0 !important;
}}

/* Pinned Chat Input at bottom - Modern Pill Container */
[data-testid="stChatInput"] {{
    background-color: #141417 !important;
    border: 1px solid #27272A !important;
    border-radius: 26px !important;
    padding: 0.35rem 0.65rem !important;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5) !important;
    transition: all 180ms ease !important;
}}

[data-testid="stChatInput"]:focus-within {{
    border-color: #3F3F46 !important;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.65), 0 0 0 1px #52525B !important;
}}

[data-testid="stChatInput"] textarea {{
    color: {COLOR_TEXT_PRIMARY} !important;
    font-size: 0.95rem !important;
    background: transparent !important;
}}

[data-testid="stChatInput"] button {{
    background-color: #27272A !important;
    border-radius: 50% !important;
    color: #F4F4F5 !important;
    width: 32px !important;
    height: 32px !important;
    border: none !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    transition: background-color 150ms ease !important;
}}

[data-testid="stChatInput"] button:hover {{
    background-color: #3F3F46 !important;
}}

/* Modern Pill Navigation Tabs */
[data-testid="stTabs"] {{
    margin-bottom: 1.25rem !important;
}}

[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    background-color: transparent !important;
    gap: 0.5rem !important;
    border-bottom: 1px solid #27272A !important;
    padding-bottom: 0.4rem !important;
}}

[data-testid="stTabs"] [data-baseweb="tab"] {{
    background-color: #18181D !important;
    border: 1px solid #29292F !important;
    border-radius: 20px !important;
    padding: 0.4rem 1.1rem !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    color: #A1A1AA !important;
    transition: all 140ms ease !important;
}}

[data-testid="stTabs"] [data-baseweb="tab"]:hover {{
    background-color: #27272A !important;
    color: #F4F4F5 !important;
}}

[data-testid="stTabs"] [aria-selected="true"] {{
    background-color: #27272A !important;
    border-color: #52525B !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
}}

[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
    display: none !important;
}}

/* ChatGPT Style Citation Pills */
.chat-citation-pill {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    background-color: {COLOR_ELEVATED};
    border: 1px solid {COLOR_BORDER};
    border-radius: 9999px;
    padding: 0.18rem 0.65rem;
    font-size: 0.76rem;
    font-weight: 500;
    color: #D4D4D8;
    text-decoration: none;
    margin-right: 0.35rem;
    margin-top: 0.35rem;
    cursor: default;
    transition: background-color 150ms ease, border-color 150ms ease;
}}

.chat-citation-pill:hover {{
    background-color: #27272E;
    border-color: {COLOR_PRIMARY}80;
    color: #FFFFFF;
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
