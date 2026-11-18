"""Markdown and HTML sanitization for safe local-first rendering.

Neutralizes untrusted external image URLs and scripts in PDF text and LLM outputs,
enforcing the local-only zero network egress invariant in the browser (INF-03).

This is deliberately a *hardening* of the existing regex pass, not a full Markdown
AST/allowlist renderer.  A complete allowlist renderer would require a parsing
dependency; the project's no-new-dependencies constraint keeps this module on a
conservative pattern pass that additionally normalizes HTML character references
before scheme checks, strips event-handler attributes, and removes SVG payloads.
"""

import html
import re

_DANGEROUS_SCHEMES = ("javascript:", "data:", "vbscript:", "file:")


def _decode_destination(value: str) -> str:
    """Decode character references and strip whitespace used to split schemes.

    Browsers ignore control/space characters embedded in URLs and decode HTML
    entities before dispatching a navigation.  Normalizing the same way lets the
    scheme checks see ``java&#x73;cript:`` as ``javascript:``.
    """
    decoded = html.unescape(value)
    return re.sub(r"[\x00-\x20\u00a0]+", "", decoded).lower()


def _is_dangerous_destination(destination: str) -> bool:
    """Return True when a link/image destination uses an executable/data scheme."""
    return _decode_destination(destination).startswith(_DANGEROUS_SCHEMES)


def _is_external_destination(destination: str) -> bool:
    """Return True when a destination points outside the local application origin."""
    normalized = _decode_destination(destination)
    return normalized.startswith(("http://", "https://", "//"))


# Destination alternation supports angle-bracket wrapping and one level of
# balanced parentheses (e.g. `javascript:alert(1)` or Wikipedia-style URLs).
_MD_DESTINATION = r"(?:<([^>\n]*)>|((?:[^()\n]|\([^()\n]*\))*))"

# Regex matching Markdown images: ![alt](url) and ![alt](<url>)
_MD_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(\s*" + _MD_DESTINATION + r"\s*\)", re.IGNORECASE)

# Regex matching Markdown links (not images): [text](url) and [text](<url>)
_MD_LINK_PATTERN = re.compile(r"(?<!!)\[([^\]]*)\]\(\s*" + _MD_DESTINATION + r"\s*\)", re.IGNORECASE)

# Any Markdown link/image destination, used for executable-scheme blocking.
_MD_ANY_LINK_PATTERN = re.compile(r"!?\[([^\]]*)\]\(\s*" + _MD_DESTINATION + r"\s*\)", re.IGNORECASE)

# Regex matching HTML img tags: <img ...>
_HTML_IMG_PATTERN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)

# Regex matching HTML anchor tags: <a ...>text</a>
_HTML_A_PATTERN = re.compile(r"<a\b([^>]*)>(.*?)<\/a\s*>", re.IGNORECASE | re.DOTALL)

# Regex matching raw script tags
_HTML_SCRIPT_PATTERN = re.compile(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script\s*>", re.IGNORECASE)

# Regex matching unsafe embedded HTML tags (iframe, object, embed, style, link,
# media, forms, and document-level redirection tags)
_UNSAFE_TAGS = "iframe|object|embed|style|link|video|audio|source|track|form|input|button|base|meta"
_HTML_UNSAFE_EMBEDS = re.compile(
    rf"<(?:{_UNSAFE_TAGS})\b[^<]*(?:(?!<\/(?:{_UNSAFE_TAGS})>)<[^<]*)*<\/(?:{_UNSAFE_TAGS})>"
    rf"|<(?:{_UNSAFE_TAGS})\b[^>]*\/?>",
    re.IGNORECASE,
)

# SVG elements can carry scripts, event handlers, and external references.  The
# generic embed pattern above cannot span nested tags, so SVG gets a dedicated
# non-greedy block matcher.  Standalone `use`/`image` references are also removed
# so a malformed/unclosed SVG cannot leave an external dereference behind.
_HTML_SVG_BLOCK = re.compile(r"<svg\b[^>]*>.*?<\/svg\s*>|<svg\b[^>]*\/?>", re.IGNORECASE | re.DOTALL)
_HTML_SVG_REF_TAG = re.compile(r"<(?:use|image|foreignObject)\b[^>]*\/?>", re.IGNORECASE)

# Inline event handlers (`onerror=`, `onload=`, `onclick=`, ...).  Matches with
# or without whitespace after a tag name slash (e.g. `<img/onerror=...>`).
_HTML_EVENT_HANDLER_ATTR = re.compile(
    r"(?P<lead>[\s/])on[a-z]{2,}\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE,
)

# Attributes that can navigate/fetch.  Values may be quoted or unquoted.
_HTML_URL_ATTR = re.compile(
    r"\s+(?:href|src|xlink:href|action|formaction|poster)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
    re.IGNORECASE,
)

# `ping` fetches tracking endpoints and has no safe local use in document output.
_HTML_PING_ATTR = re.compile(r"\s+ping\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)

# srcset can trigger external fetches without a src= attribute
_HTML_SRCSET_ATTR_PATTERN = re.compile(r"\s+srcset\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)

# Inline CSS url(...) can trigger external fetches without an href/src attribute
_HTML_STYLE_URL_ATTR_PATTERN = re.compile(
    r"\s+style\s*=\s*(?:\"[^\"]*url\s*\([^\"]*\"|'[^']*url\s*\([^']*')",
    re.IGNORECASE,
)

# Autolinks / raw text using an executable or data scheme
_DANGEROUS_AUTOLINK_PATTERN = re.compile(r"<([^>\s]*)>", re.IGNORECASE)

# Markdown autolinks: <https://example.com>
_MD_AUTOLINK_PATTERN = re.compile(r"<(https?://[^>\s]+|//[^>\s]+)>", re.IGNORECASE)

# Bare URLs (Streamlit/CommonMark may render these as clickable links)
_BARE_URL_PATTERN = re.compile(r"(?<![\w`])(?:https?://|//)[^\s<>()\[\]`]+", re.IGNORECASE)

# Reference-style link definitions: [id]: https://example.com
_MD_REF_DEF_PATTERN = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+).*$", re.MULTILINE | re.IGNORECASE)


def _attr_value(match: re.Match[str]) -> str:
    """Extract the first non-None group from an attribute-value regex match."""
    for group in match.groups():
        if group is not None:
            return group
    return ""


def _destination(match: re.Match[str]) -> str:
    """Extract a Markdown destination from the angle/non-angle alternation."""
    return match.group(2) if match.group(2) is not None else (match.group(3) or "")


def sanitize_markdown_for_local(text: str, allow_external: bool = False) -> str:
    """Sanitize Markdown and HTML content to prevent browser-triggered network requests.

    Args:
        text: Raw Markdown or generated LLM text.
        allow_external: If True, external links and images are preserved (cloud mode).
                        If False (default), external links and images are neutralized.
                        Executable/data schemes, event handlers, scripts, and SVG
                        payloads are always removed regardless of this flag.

    Returns:
        Sanitized Markdown text safe for browser rendering in local mode.
    """
    if not text:
        return ""

    sanitized = text

    # Strip dangerous executable and embeddable HTML elements
    sanitized = _HTML_SCRIPT_PATTERN.sub("[Script removed]", sanitized)
    sanitized = _HTML_SVG_BLOCK.sub("[Embedded element removed]", sanitized)
    sanitized = _HTML_SVG_REF_TAG.sub("[Embedded element removed]", sanitized)
    sanitized = _HTML_UNSAFE_EMBEDS.sub("[Embedded element removed]", sanitized)

    # Inline event handlers execute script regardless of link consent.
    sanitized = _HTML_EVENT_HANDLER_ATTR.sub(lambda m: m.group("lead"), sanitized)

    # Executable and data schemes are never safe in rendered document output.
    def _replace_dangerous_md(match: re.Match[str]) -> str:
        if _is_dangerous_destination(_destination(match)):
            return "`[blocked link]`"
        return match.group(0)

    sanitized = _MD_ANY_LINK_PATTERN.sub(_replace_dangerous_md, sanitized)

    def _replace_dangerous_attr(match: re.Match[str]) -> str:
        if _is_dangerous_destination(_attr_value(match)):
            return ""
        return match.group(0)

    sanitized = _HTML_URL_ATTR.sub(_replace_dangerous_attr, sanitized)
    sanitized = _HTML_PING_ATTR.sub("", sanitized)

    def _replace_dangerous_autolink(match: re.Match[str]) -> str:
        if _is_dangerous_destination(_attr_value(match)):
            return "`[external link blocked]`"
        return match.group(0)

    sanitized = _DANGEROUS_AUTOLINK_PATTERN.sub(_replace_dangerous_autolink, sanitized)

    def _replace_ref_def(match: re.Match[str]) -> str:
        destination = match.group(1)
        if _is_dangerous_destination(destination):
            return "`[blocked link definition]`"
        if not allow_external and _is_external_destination(destination):
            return "`[external link definition blocked]`"
        return match.group(0)

    sanitized = _MD_REF_DEF_PATTERN.sub(_replace_ref_def, sanitized)

    if not allow_external:
        # Attributes that can initiate network requests without a standard href/src
        sanitized = _HTML_SRCSET_ATTR_PATTERN.sub("", sanitized)
        sanitized = _HTML_STYLE_URL_ATTR_PATTERN.sub("", sanitized)

        # Replace external Markdown images with a clean text placeholder
        def _replace_md_img(match: re.Match[str]) -> str:
            alt = match.group(1).strip() or "image"
            if _is_external_destination(_destination(match)):
                return f"`[Blocked external image: {alt}]`"
            return match.group(0)

        sanitized = _MD_IMAGE_PATTERN.sub(_replace_md_img, sanitized)

        # Replace external HTML images with a text placeholder
        def _replace_html_img(match: re.Match[str]) -> str:
            src_attr = re.search(
                r"\bsrc\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
                match.group(0),
                re.IGNORECASE,
            )
            if src_attr is not None and _is_external_destination(_attr_value(src_attr)):
                return "`[Blocked external image]`"
            return match.group(0)

        sanitized = _HTML_IMG_PATTERN.sub(_replace_html_img, sanitized)

        # Neutralize external Markdown links to eliminate outbound tracking
        def _replace_md_link(match: re.Match[str]) -> str:
            label = match.group(1).strip()
            if _is_external_destination(_destination(match)):
                return f"`{label}` *(external link blocked)*"
            return match.group(0)

        sanitized = _MD_LINK_PATTERN.sub(_replace_md_link, sanitized)

        # Neutralize HTML anchor tags pointing off-origin
        def _replace_html_a(match: re.Match[str]) -> str:
            label = match.group(2).strip()
            href_attr = re.search(
                r"\bhref\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
                match.group(1),
                re.IGNORECASE,
            )
            if href_attr is not None and _is_external_destination(_attr_value(href_attr)):
                return f"`{label}` *(external link blocked)*"
            return match.group(0)

        sanitized = _HTML_A_PATTERN.sub(_replace_html_a, sanitized)

        # Autolinks and bare URLs are clickable in CommonMark/Streamlit even without
        # explicit Markdown link syntax.
        sanitized = _MD_AUTOLINK_PATTERN.sub("`[external link blocked]`", sanitized)
        sanitized = _BARE_URL_PATTERN.sub("`[external link blocked]`", sanitized)

    return sanitized


# Reusable alias
sanitize_display_markdown = sanitize_markdown_for_local
