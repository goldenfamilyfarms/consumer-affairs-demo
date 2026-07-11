"""REST API serializers.

BrandCardSerializer delivers the per-card payload for GET /api/brands/.
Each row carries: name, slug, industry name, computed average rating,
review count, short description (brand body excerpt), and top review snippet.

The top-review rule (Req 10.6): highest rating >= 1 for the brand; ties broken
by most recent wp_post_date. The snippet is the review body truncated to ~160
characters on a word boundary. A brand with zero qualifying reviews yields null
(Req 10.7).
"""

import html as _html

from django.db.models import OuterRef, Prefetch, Subquery
from django.utils.html import strip_tags

from rest_framework import serializers

from catalog.models import Brand, Review


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def excerpt(text: str, max_chars: int = 160) -> str | None:
    """Truncate *text* to approximately *max_chars* on a word boundary.

    The WordPress ``post_content`` this operates on is HTML, so tags are
    stripped and entities unescaped first to yield clean plain text for a card
    excerpt.  Returns ``None`` when the input is empty/whitespace-only.  If the
    text fits within *max_chars* it is returned unchanged (stripped).
    Otherwise we cut at the last space at or before *max_chars* and append an
    ellipsis.
    """
    if not text:
        return None
    # post_content is HTML — reduce to plain text before truncating.
    text = _html.unescape(strip_tags(text)).strip()
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    # Find the last space at or before max_chars to cut on a word boundary.
    cut = text.rfind(" ", 0, max_chars)
    if cut == -1:
        # Single very long word — hard cut.
        cut = max_chars
    return text[:cut] + "\u2026"


# ---------------------------------------------------------------------------
# Prefetch helper
# ---------------------------------------------------------------------------


def top_review_prefetch() -> Prefetch:
    """Return a Prefetch that loads *exactly one* top review per brand.

    Selection rule (Req 10.6):
      1. Only reviews with rating >= 1 qualify.
      2. Among qualifying reviews, pick the one with the highest rating.
      3. Ties broken by most recent wp_post_date (descending).

    Rather than pull every qualifying review per brand and read index 0 (which
    would drag thousands of rows per brand into Python at scale, only to discard
    all but one), the Prefetch queryset is narrowed with a correlated subquery to
    the single winning review id per brand. This yields one row per brand in a
    single query, and is cross-database (the correlated ``[:1]`` subquery works
    on SQLite and Postgres alike — no ``DISTINCT ON``/window dependency).

    Results are attached as ``brand._top_review_cache`` — a list with at most one
    element; the serializer reads element 0.
    """
    top_id_per_brand = (
        Review.objects.filter(brand=OuterRef("brand"), rating__gte=1)
        .order_by("-rating", "-wp_post_date")
        .values("pk")[:1]
    )
    qs = Review.objects.filter(rating__gte=1, pk__in=Subquery(top_id_per_brand))
    return Prefetch(
        "reviews",
        queryset=qs,
        to_attr="_top_review_cache",
    )


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------


class IndustrySerializer(serializers.Serializer):
    """Read-only serializer for the industry filter options.

    Backs ``GET /api/industries/`` so the React filter control can load the full
    set of industries independently of the current brand result set (avoiding a
    cold-start where the dropdown is empty until brands load, or incomplete when
    a filter is already applied).
    """

    name = serializers.CharField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    brand_count = serializers.IntegerField(read_only=True)


class BrandCardSerializer(serializers.Serializer):
    """Read-only serializer for a brand card in the listing API.

    Expects instances loaded via ``Brand.objects.with_stats()`` with the
    ``top_review_prefetch()`` applied so that annotated values and the top
    review are available without N+1 queries.
    """

    name = serializers.CharField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    industry = serializers.SerializerMethodField()
    industry_slug = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.IntegerField(read_only=True)
    short_description = serializers.SerializerMethodField()
    top_review_snippet = serializers.SerializerMethodField()

    def get_industry(self, brand: Brand) -> str:
        """Return the industry name string (display label)."""
        return brand.industry.name

    def get_industry_slug(self, brand: Brand) -> str:
        """Return the industry slug — the value the API filters on.

        Exposed so a client can round-trip the exact ``industry`` filter param
        (the API validates against the slug, not the display name).
        """
        return brand.industry.slug

    def get_average_rating(self, brand: Brand):
        """Return computed average rating rounded to 2 decimals, or null."""
        avg = brand.computed_average_rating
        if avg is None:
            return None
        return round(float(avg), 2)

    def get_short_description(self, brand: Brand) -> str | None:
        """Return ~160-char word-boundary excerpt of the brand body."""
        return excerpt(brand.body)

    def get_top_review_snippet(self, brand: Brand) -> str | None:
        """Return ~160-char excerpt of the top review's body, or null.

        Relies on the ``_top_review_cache`` list populated by
        :func:`top_review_prefetch`.  When the prefetch has not been applied
        (e.g. in tests without it), falls back to a direct query.
        """
        top_reviews = getattr(brand, "_top_review_cache", None)

        if top_reviews is None:
            # Fallback: query directly (single brand usage / tests).
            top_review = (
                brand.reviews.filter(rating__gte=1)
                .order_by("-rating", "-wp_post_date")
                .first()
            )
        else:
            top_review = top_reviews[0] if top_reviews else None

        if top_review is None:
            return None
        return excerpt(top_review.body)
