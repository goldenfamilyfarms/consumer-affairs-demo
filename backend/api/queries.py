"""Framework-agnostic query helpers for the brand listing API.

These are shared building blocks (excerpt text, the one-row top-review prefetch,
and the annotated/filtered/ordered queryset). They have no web-framework
dependency, so the Ninja endpoints — or anything else — can reuse them.
"""

from __future__ import annotations

import html as _html

from django.db.models import F, OuterRef, Prefetch, Subquery
from django.utils.html import strip_tags

from catalog.models import Brand, Review


def excerpt(text: str, max_chars: int = 160) -> str | None:
    """Reduce migrated WordPress HTML to a ~max_chars plain-text excerpt.

    Strips tags + unescapes entities first, then cuts on a word boundary and
    appends an ellipsis. Returns ``None`` for empty/whitespace-only input.
    """
    if not text:
        return None
    text = _html.unescape(strip_tags(text)).strip()
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    cut = text.rfind(" ", 0, max_chars)
    if cut == -1:
        cut = max_chars
    return text[:cut] + "\u2026"


def top_review_prefetch() -> Prefetch:
    """Prefetch exactly one top review per brand (highest rating, latest date).

    Uses a correlated subquery so it pulls one row per brand in a single query,
    cross-database (no ``DISTINCT ON``/window dependency). Attached as
    ``brand._top_review_cache`` (a list with at most one element).
    """
    top_id_per_brand = (
        Review.objects.filter(brand=OuterRef("brand"), rating__gte=1)
        .order_by("-rating", "-wp_post_date")
        .values("pk")[:1]
    )
    qs = Review.objects.filter(rating__gte=1, pk__in=Subquery(top_id_per_brand))
    return Prefetch("reviews", queryset=qs, to_attr="_top_review_cache")


def brand_card_queryset(industry_slug, sort_field, direction):
    """Build the annotated, filtered, ordered brand queryset for the listing.

    ``sort_field`` is an annotation name (from validation), ``direction`` is
    ``asc``/``desc``. Null ratings sort last regardless of direction; a stable
    ``slug`` tiebreak keeps pagination deterministic.
    """
    qs = (
        Brand.objects.with_stats()
        .select_related("industry")
        .prefetch_related(top_review_prefetch())
    )
    if industry_slug:
        qs = qs.filter(industry__slug=industry_slug)

    order = F(sort_field)
    ordering = (
        order.asc(nulls_last=True) if direction == "asc" else order.desc(nulls_last=True)
    )
    return qs.order_by(ordering, "slug")


def top_review_for(brand: Brand):
    """Return a brand's top review, preferring the prefetch, else a direct query."""
    cache = getattr(brand, "_top_review_cache", None)
    if cache is not None:
        return cache[0] if cache else None
    return (
        brand.reviews.filter(rating__gte=1)
        .order_by("-rating", "-wp_post_date")
        .first()
    )
