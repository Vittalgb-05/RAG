"""Reusable UI components for the AMOLED document workspace."""

import html
from pathlib import Path
import streamlit as st

ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
BRAND_MARK_PATH = Path(__file__).resolve().parent.parent / "assets" / "brand_mark.svg"

# Icon cache
_ICON_CACHE: dict[str, str] = {}


def get_svg_icon(name: str, size: int = 18, color: str | None = None) -> str:
    """Load and format a local monochrome SVG icon.

    Args:
        name: Name of icon file without .svg extension.
        size: Width and height in pixels.
        color: Optional CSS color override (default: currentColor).

    Returns:
        Formatted SVG markup string.
    """
    if name not in _ICON_CACHE:
        icon_path = ICONS_DIR / f"{name}.svg"
        if icon_path.exists():
            _ICON_CACHE[name] = icon_path.read_text(encoding="utf-8")
        else:
            _ICON_CACHE[name] = ""

    raw_svg = _ICON_CACHE[name]
    if not raw_svg:
        return ""

    # Adjust width and height
    formatted = raw_svg.replace('width="18"', f'width="{size}"').replace('height="18"', f'height="{size}"')
    formatted = formatted.replace('width="20"', f'width="{size}"').replace('height="20"', f'height="{size}"')
    if color:
        formatted = formatted.replace('stroke="currentColor"', f'stroke="{color}"')
    return formatted


def get_brand_mark_svg(size: int = 36) -> str:
    """Load brand mark SVG markup."""
    if BRAND_MARK_PATH.exists():
        raw = BRAND_MARK_PATH.read_text(encoding="utf-8")
        return raw.replace('width="40"', f'width="{size}"').replace('height="40"', f'height="{size}"')
    return ""


def render_brand_header() -> None:
    """Render the sidebar brand mark and application identifier."""
    brand_svg = get_brand_mark_svg(size=28)
    header_html = (
        f'<div style="display: flex; align-items: center; gap: 0.65rem; margin-bottom: 0.25rem;">'
        f"{brand_svg}"
        f"<div>"
        f'<div style="font-size: 0.95rem; font-weight: 700; color: #F4F4F5; letter-spacing: -0.02em;">PAPER / INTELLIGENCE</div>'
        f'<div style="font-size: 0.72rem; color: #A1A1AA; font-weight: 500;">Local-First PDF Intelligence</div>'
        f"</div></div>"
    )
    if hasattr(st.sidebar, "html"):
        st.sidebar.html(header_html)
    else:
        st.sidebar.markdown(header_html, unsafe_allow_html=True)


def render_stat_card(label: str, value: str | int, subtext: str = "", icon_name: str = "document") -> None:
    """Render a clean metric card with monochrome icon."""
    icon_svg = get_svg_icon(icon_name, size=18, color="#A78BFA")
    subtext_html = f'<div class="stat-subtext">{html.escape(str(subtext))}</div>' if subtext else ""
    card_html = (
        f'<div class="amoled-card">'
        f'<div style="display: flex; justify-content: space-between; align-items: center;">'
        f'<span class="stat-label">{html.escape(str(label))}</span>{icon_svg}</div>'
        f'<div class="stat-value">{html.escape(str(value))}</div>'
        f"{subtext_html}</div>"
    )
    if hasattr(st, "html"):
        st.html(card_html)
    else:
        st.markdown(card_html, unsafe_allow_html=True)


def render_status_pill(text: str, variant: str = "local") -> str:
    """Generate HTML markup for an AMOLED status badge."""
    color = "#5EEAD4" if variant == "local" else ("#A78BFA" if variant == "cloud" else "#F87171")
    icon_name = "check" if variant == "local" else ("cloud" if variant == "cloud" else "alert")
    icon_svg = get_svg_icon(icon_name, size=12, color=color)
    safe_text = html.escape(text)
    return f'<span class="status-badge {variant}">{icon_svg} {safe_text}</span>'


def render_empty_state(title: str, message: str, icon_name: str = "document") -> None:
    """Render a clean empty state card."""
    icon_svg = get_svg_icon(icon_name, size=28, color="#A1A1AA")
    safe_title = html.escape(title)
    safe_msg = html.escape(message)
    empty_html = (
        f'<div class="amoled-card" style="text-align: center; padding: 2rem 1.25rem;">'
        f'<div style="margin-bottom: 0.65rem;">{icon_svg}</div>'
        f'<div style="font-size: 0.95rem; font-weight: 600; color: #F4F4F5; margin-bottom: 0.25rem;">{safe_title}</div>'
        f'<div style="font-size: 0.825rem; color: #A1A1AA; max-width: 380px; margin: 0 auto;">{safe_msg}</div>'
        f"</div>"
    )
    if hasattr(st, "html"):
        st.html(empty_html)
    else:
        st.markdown(empty_html, unsafe_allow_html=True)


def render_citation_chip(
    doc_id: str,
    page: int,
    filename: str,
    rank: int | None = None,
    auto_attributed: bool = False,
) -> str:
    """Render an evidence citation chip, marking auto-attributed citations distinctly."""
    prefix = f"[E{rank}] " if rank is not None else ""
    safe_filename = html.escape(filename)
    state = "auto" if auto_attributed else "direct"
    icon_color = "#C4B5FD" if auto_attributed else "#5EEAD4"
    background = "#18181D"
    border = "1px dashed #7C3AED" if auto_attributed else "1px solid #29292F"
    label = "Auto-attributed" if auto_attributed else "Direct citation"
    marker = (
        ' <span style="font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.04em; '
        'opacity: 0.85;">(auto)</span>'
        if auto_attributed
        else ""
    )
    doc_icon = get_svg_icon("document", size=12, color=icon_color)
    return (
        f'<span data-citation-state="{state}" title="{label}" '
        f'style="display: inline-flex; align-items: center; gap: 0.25rem; background: {background}; '
        f"border: {border}; border-radius: 6px; padding: 0.15rem 0.5rem; font-size: 0.75rem; color: {icon_color}; "
        f'font-weight: 500;">'
        f"{doc_icon} {prefix}{safe_filename} · p. {page}{marker}</span>"
    )


def render_chatgpt_citation_pill(
    filename: str,
    page: int,
    excerpt: str = "",
    rank: int | None = None,
    auto_attributed: bool = False,
) -> str:
    """Render a clean ChatGPT-style citation badge with hover tooltip containing excerpt."""
    safe_name = html.escape(filename)
    safe_excerpt = html.escape(excerpt.strip()[:350]) if excerpt else ""
    doc_svg = get_svg_icon("document", size=12, color="#9CA3AF")
    title_attr = f'title="{safe_excerpt}"' if safe_excerpt else ""
    rank_prefix = f"[E{rank}] " if rank is not None else ""
    return (
        f'<span class="chat-citation-pill" {title_attr}>'
        f"{doc_svg}<span>{rank_prefix}{safe_name} · p. {page}</span>"
        f"</span>"
    )
