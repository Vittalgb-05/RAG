"""Unit tests for local markdown sanitization and external request neutralization."""

from ui.sanitizer import sanitize_markdown_for_local


def test_sanitize_blocks_external_markdown_images_in_local_mode() -> None:
    raw_md = "Here is an image: ![malicious tracker](https://evil.com/pixel.png) and text."
    sanitized = sanitize_markdown_for_local(raw_md, allow_external=False)
    assert "https://evil.com/pixel.png" not in sanitized
    assert "[Blocked external image: malicious tracker]" in sanitized
    assert "Here is an image:" in sanitized
    assert "and text." in sanitized


def test_sanitize_allows_external_images_when_consented() -> None:
    raw_md = "Here is an image: ![banner](https://example.com/banner.png)"
    sanitized = sanitize_markdown_for_local(raw_md, allow_external=True)
    assert "![banner](https://example.com/banner.png)" in sanitized


def test_sanitize_blocks_raw_html_img_tags() -> None:
    raw_html = 'Text with <img src="http://tracker.com/track.gif" width="1"/> embedded.'
    sanitized = sanitize_markdown_for_local(raw_html, allow_external=False)
    assert "http://tracker.com/track.gif" not in sanitized
    assert "[Blocked external image]" in sanitized


def test_sanitize_strips_scripts() -> None:
    raw = 'Hello <script>alert("pwned")</script> World'
    sanitized = sanitize_markdown_for_local(raw)
    assert "<script>" not in sanitized
    assert "alert" not in sanitized
    assert "Hello [Script removed] World" in sanitized
