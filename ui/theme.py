"""Theme tokens, custom CSS styles, and subtle motion transitions for AMOLED workspace."""

import streamlit as st

# AMOLED design tokens (single source of truth for the rebuilt UI).
# 8px spacing scale; 12-16px radii; restrained violet accent, green success.
COLOR_BG = "#09090B"
COLOR_SURFACE = "#111114"
COLOR_ELEVATED = "#19191D"
COLOR_BORDER = "#29292F"
COLOR_PRIMARY = "#A78BFA"
COLOR_SECONDARY = "#34D399"
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

/* Main content column - centered ~960px */
.block-container {{
    max-width: 960px !important;
    padding-top: 24px !important;
    padding-bottom: 104px !important;
    padding-left: 24px !important;
    padding-right: 24px !important;
}}

[data-testid="stSidebar"] {{
    background-color: {COLOR_SURFACE};
    border-right: 1px solid {COLOR_BORDER};
    min-width: 240px !important;
    max-width: 280px !important;
}}

[data-testid="stSidebar"] > div:first-child {{
    padding-top: 16px;
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

/* User chat message bubble - compact elevated container.
   Streamlit 1.66 renamed the avatar test ids (chatAvatarIcon-* -> stChatMessageAvatar*);
   both spellings are matched so the bubble styling survives the version it runs on. */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
    background-color: {COLOR_ELEVATED} !important;
    border: 1px solid {COLOR_BORDER} !important;
    border-radius: 16px !important;
    padding: 0.75rem 1.15rem !important;
    margin-left: auto !important;
    max-width: 85% !important;
}}

/* Assistant chat message - readable uncluttered flow */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {{
    background-color: transparent !important;
    border: none !important;
    padding: 0 !important;
}}

/* Pinned Composer - one wide rounded dark surface */
[data-testid="stChatInput"] {{
    background-color: {COLOR_ELEVATED} !important;
    border: 1px solid {COLOR_BORDER} !important;
    border-radius: 16px !important;
    padding: 0.35rem 0.65rem !important;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5) !important;
    transition: all 180ms ease !important;
}}

[data-testid="stChatInput"]:focus-within {{
    border-color: {COLOR_PRIMARY}80 !important;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.55) !important;
}}

[data-testid="stChatInput"] textarea {{
    color: {COLOR_TEXT_PRIMARY} !important;
    font-size: 0.95rem !important;
    background: transparent !important;
}}

[data-testid="stChatInput"] button {{
    background-color: {COLOR_BORDER} !important;
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


/* Terminal-style backend notifications, lower-right, non-overlapping */
.st-key-terminal_notifications {{
    position: fixed !important;
    right: 24px !important;
    bottom: 104px !important;
    width: 360px !important;
    max-width: calc(100vw - 48px) !important;
    z-index: 9999 !important;
    background-color: {COLOR_SURFACE} !important;
    border: 1px solid {COLOR_BORDER} !important;
    border-radius: 12px !important;
    padding: 8px 12px !important;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55) !important;
}}

.terminal-line {{
    font-family: "JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace !important;
    font-size: 0.72rem !important;
    line-height: 1.45 !important;
    color: {COLOR_TEXT_MUTED} !important;
    padding: 4px 8px !important;
    margin: 2px 0 !important;
    word-break: break-word !important;
}}

.terminal-time {{ color: #71717A !important; }}
.terminal-kind {{ font-weight: 700 !important; letter-spacing: 0.04em !important; }}
.terminal-message {{ color: {COLOR_TEXT_PRIMARY} !important; }}
.terminal-more {{ font-size: 0.68rem !important; color: #71717A !important; padding-left: 8px !important; }}

/* Sidebar sections and truthful provider status */
.sidebar-section-label {{
    font-size: 0.68rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: {COLOR_TEXT_MUTED} !important;
    font-weight: 700 !important;
    margin: 1.1rem 0 0.4rem !important;
}}

.provider-status {{
    display: flex !important;
    align-items: center !important;
    gap: 0.5rem !important;
    font-size: 0.78rem !important;
    color: {COLOR_TEXT_PRIMARY} !important;
    padding: 0.35rem 0 !important;
}}

.provider-dot {{
    width: 7px !important;
    height: 7px !important;
    border-radius: 50% !important;
    flex: 0 0 auto !important;
}}

.sidebar-meta {{
    font-size: 0.72rem !important;
    color: {COLOR_TEXT_MUTED} !important;
}}

/* Compact sidebar rhythm so Settings remains reachable at laptop heights */
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
    gap: 0.45rem !important;
}}
[data-testid="stSidebar"] hr {{
    margin: 0.25rem 0 !important;
}}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
    margin-bottom: 0 !important;
}}

/* Keep the sidebar scrollbar visually quiet on dark backgrounds */
[data-testid="stSidebar"] *::-webkit-scrollbar {{
    width: 6px;
    height: 6px;
}}
[data-testid="stSidebar"] *::-webkit-scrollbar-thumb {{
    background: {COLOR_BORDER};
    border-radius: 3px;
}}
[data-testid="stSidebar"] *::-webkit-scrollbar-track {{
    background: transparent;
}}

/* Suggestion grid stays readable without overlaps on narrow viewports */
@media (max-width: 900px) {{
    .st-key-hero_suggestions [data-testid="stHorizontalBlock"] {{
        flex-wrap: wrap !important;
        gap: 0.5rem !important;
    }}
    .st-key-hero_suggestions [data-testid="stColumn"] {{
        flex: 1 1 calc(50% - 0.5rem) !important;
        min-width: calc(50% - 0.5rem) !important;
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
