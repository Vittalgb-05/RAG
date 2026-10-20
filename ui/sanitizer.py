"""Markdown and HTML sanitization for safe local-first rendering.

Neutralizes untrusted external image URLs and scripts in PDF text and LLM outputs,
enforcing the local-only zero network egress invariant in the browser (INF-03).
"""

import re

# Regex matching Markdown images: ![alt](url)
_MD_IMAGE_PATTERN = re.compile(r"!\[(.*?)\]\((https?://[^\)]+|\/\/[^\)]+)\)", re.IGNORECASE)

# Regex matching HTML img tags: <img ... src="..." ...>
_HTML_IMG_PATTERN = re.compile(r"<img\s+[^>]*src=[\"']?(https?:)?//[^\"'>]+[\"']?[^>]*>", re.IGNORECASE)

# Regex matching Markdown links: [text](url)
_MD_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+|\/\/[^\)]+)\)", re.IGNORECASE)

# Regex matching HTML anchor tags: <a ... href="..." ...>text</a>
_HTML_A_PATTERN = re.compile(
    r"<a\s+[^>]*href=[\"']?(?:https?:)?//[^\"'>]+[\"']?[^>]*>(.*?)<\/a>", re.IGNORECASE | re.DOTALL
)

# Regex matching raw script tags
_HTML_SCRIPT_PATTERN = re.compile(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", re.IGNORECASE)

# Regex matching unsafe embedded HTML tags (iframe, object, embed, style, link)
_HTML_UNSAFE_EMBEDS = re.compile(
    r"<(?:iframe|object|embed|style|link)\b[^<]*(?:(?!<\/(?:iframe|object|embed|style|link)>)<[^<]*)*<\/(?:iframe|object|embed|style|link)>|<(?:iframe|object|embed|style|link)\b[^>]*\/?>",
    re.IGNORECASE,
)


def sanitize_markdown_for_local(text: str, allow_external: bool = False) -> str:
    """Sanitize Markdown and HTML content to prevent browser-triggered network requests.

    Args:
        text: Raw Markdown or generated LLM text.
        allow_external: If True, external links and images are preserved (cloud mode).
                        If False (default), external links and images are neutralized.

    Returns:
        Sanitized Markdown text safe for browser rendering in local mode.
    """
    if not text:
        return ""

    sanitized = text

    # Strip dangerous executable and embeddable HTML elements
    sanitized = _HTML_SCRIPT_PATTERN.sub("[Script removed]", sanitized)
    sanitized = _HTML_UNSAFE_EMBEDS.sub("[Embedded element removed]", sanitized)

    if not allow_external:
        # Replace external Markdown images with a clean text placeholder
        def _replace_md_img(match: re.Match[str]) -> str:
            alt = match.group(1).strip() or "image"
            return f"`[Blocked external image: {alt}]`"

        sanitized = _MD_IMAGE_PATTERN.sub(_replace_md_img, sanitized)

        # Replace HTML images with a text placeholder
        sanitized = _HTML_IMG_PATTERN.sub("`[Blocked external image]`", sanitized)

        # Neutralize external Markdown links to eliminate outbound tracking
        def _replace_md_link(match: re.Match[str]) -> str:
            label = match.group(1).strip()
            return f"`{label}` *(external link blocked)*"

        sanitized = _MD_LINK_PATTERN.sub(_replace_md_link, sanitized)

        # Neutralize HTML anchor tags
        def _replace_html_a(match: re.Match[str]) -> str:
            label = match.group(1).strip()
            return f"`{label}` *(external link blocked)*"

        sanitized = _HTML_A_PATTERN.sub(_replace_html_a, sanitized)

    return sanitized


# Reusable alias
sanitize_display_markdown = sanitize_markdown_for_local
