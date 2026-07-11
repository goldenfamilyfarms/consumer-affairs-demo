"""Tests for the ``sanitize_html`` template filter.

The detail pages render migrated WordPress ``post_content`` as real HTML, so
the sanitizer must keep legitimate formatting while stripping anything that
could execute (stored-XSS defense).
"""

from catalog.templatetags.catalog_extras import sanitize_html


def test_preserves_safe_formatting_tags():
    html = "<p>Great service with a <strong>fast</strong> claim process.</p>"
    out = str(sanitize_html(html))
    assert "<p>" in out
    assert "<strong>fast</strong>" in out


def test_strips_script_tags_and_content():
    out = str(sanitize_html("<p>ok</p><script>alert('xss')</script>"))
    assert "<script" not in out
    assert "alert(" not in out
    assert "<p>ok</p>" in out


def test_strips_event_handler_attributes():
    out = str(sanitize_html('<p onclick="steal()">hi</p>'))
    assert "onclick" not in out
    assert ">hi<" in out


def test_strips_javascript_url_on_links():
    out = str(sanitize_html('<a href="javascript:alert(1)">click</a>'))
    assert "javascript:" not in out


def test_keeps_safe_link_href():
    out = str(sanitize_html('<a href="https://example.com">site</a>'))
    assert 'href="https://example.com"' in out


def test_empty_input_returns_empty_string():
    assert sanitize_html("") == ""
    assert sanitize_html(None) == ""
