"""Template filters for the catalog app.

``sanitize_html`` renders migrated WordPress ``post_content`` as HTML while
stripping anything dangerous. The detail pages need real markup (paragraphs,
links, emphasis) rather than escaped ``<p>`` text, but rendering stored content
with a bare ``|safe`` is a stored-XSS vector if that content is ever tampered
with. Running it through an allowlist sanitizer (nh3 / ammonia) at render time
keeps the formatting while dropping ``<script>``, event handlers, ``javascript:``
URLs, and other unsafe constructs — defense-in-depth regardless of how the row
got into the database.
"""

from __future__ import annotations

import nh3

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Formatting tags a migrated review/brand body legitimately uses. Everything
# else (script, style, iframe, event-handler attributes, javascript: URLs) is
# stripped by nh3.
_ALLOWED_TAGS = {
    "p", "br", "hr",
    "a", "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "code",
    "span", "div",
}
# nh3 manages the ``rel`` attribute on links itself (it adds
# ``rel="noopener noreferrer"`` via its ``link_rel`` default), so ``rel`` must
# not appear in this allowlist.
_ALLOWED_ATTRIBUTES = {"a": {"href", "title", "target"}}


@register.filter(name="sanitize_html")
def sanitize_html(value: object):
    """Return *value* as sanitized, render-safe HTML.

    Empty/None yields an empty string. The result is marked safe because nh3
    guarantees the output contains only allowlisted tags/attributes.
    """
    if not value:
        return ""
    cleaned = nh3.clean(
        str(value),
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
    )
    return mark_safe(cleaned)
