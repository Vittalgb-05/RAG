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


def test_sanitize_blocks_external_links_in_local_mode() -> None:
    raw = "Refer to [documentation](https://attacker.example/leak) for details."
    sanitized = sanitize_markdown_for_local(raw, allow_external=False)
    assert "https://attacker.example/leak" not in sanitized
    assert "`documentation` *(external link blocked)*" in sanitized


def test_sanitize_allows_external_links_in_cloud_mode() -> None:
    raw = "Refer to [documentation](https://example.com/guide) for details."
    sanitized = sanitize_markdown_for_local(raw, allow_external=True)
    assert "[documentation](https://example.com/guide)" in sanitized


def test_sanitize_strips_unsafe_embeds() -> None:
    raw = '<iframe src="https://evil.com"></iframe><style>body{background:red;}</style>Content'
    sanitized = sanitize_markdown_for_local(raw)
    assert "<iframe" not in sanitized
    assert "<style" not in sanitized
    assert "Content" in sanitized


def test_sanitize_blocks_dangerous_markdown_schemes() -> None:
    raw = "[click](javascript:alert(1)) and ![x](data:image/png;base64,AAAA)"
    sanitized = sanitize_markdown_for_local(raw, allow_external=False)
    assert "javascript:" not in sanitized
    assert "data:" not in sanitized
    assert "[blocked link]" in sanitized


def test_sanitize_strips_srcset_and_inline_style_urls() -> None:
    raw = (
        '<img src="local.png" srcset="https://evil.example/a.png 1x">'
        '<div style="background:url(https://evil.example/b.png)">x</div>'
    )
    sanitized = sanitize_markdown_for_local(raw, allow_external=False)
    assert "evil.example" not in sanitized
    assert "srcset" not in sanitized.lower()
    assert "url(" not in sanitized.lower()


def test_sanitize_removes_svg_use_href() -> None:
    raw = '<svg><use href="https://evil.example/icon.svg#x"></use></svg>'
    sanitized = sanitize_markdown_for_local(raw, allow_external=False)
    assert "evil.example" not in sanitized
    assert "<use" not in sanitized.lower()
