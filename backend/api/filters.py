"""Query-parameter validation for the brand listing endpoint.

Validation is centralized here and run before the queryset is built so every
invalid value produces a clean ``400`` with ``{"detail": "..."}`` (Req 10.3,
10.4, 10.5, 11.4, 11.5, 11.7) rather than a silent no-op or a 500.

The ``sort`` allowlist is deliberately decoupled from database column names:
the public value (``avg_rating`` / ``review_count``) maps to the annotated
field produced by ``Brand.objects.with_stats()``.  This keeps the API contract
stable even if the annotation names change.
"""

from rest_framework.exceptions import ValidationError

from catalog.cache import get_industry_slugs

# Public sort value -> annotated field on Brand.objects.with_stats().
SORT_FIELDS = {
    "avg_rating": "computed_average_rating",
    "review_count": "review_count",
}

# Allowed sort directions.
SORT_DIRECTIONS = ("asc", "desc")

# Default sort when the client omits `sort` / `dir`.
DEFAULT_SORT = "avg_rating"
DEFAULT_DIRECTION = "desc"


def validate_industry(slug):
    """Validate an ``industry`` slug filter.

    Returns the slug when it matches an existing Industry, ``None`` when the
    parameter was omitted/blank (no filtering), and raises ``ValidationError``
    (→ 400) for an unknown slug (Req 10.3, 11.4).
    """
    if not slug:
        return None
    # Membership test against the cached slug set (invalidated on any Industry
    # change) instead of a per-request EXISTS query.
    if slug not in get_industry_slugs():
        raise ValidationError(
            {"detail": f"Invalid filter value: no industry with slug '{slug}'."}
        )
    return slug


def validate_sort(sort):
    """Validate the ``sort`` parameter against the allowlist (Req 10.4, 10.5).

    Returns the annotated field name to order by.  Falls back to the default
    sort when omitted; raises ``ValidationError`` (→ 400) for an unknown value
    (Req 11.5).
    """
    if not sort:
        sort = DEFAULT_SORT
    if sort not in SORT_FIELDS:
        allowed = ", ".join(sorted(SORT_FIELDS))
        raise ValidationError(
            {"detail": f"Invalid sort value '{sort}'. Allowed values: {allowed}."}
        )
    return SORT_FIELDS[sort]


def validate_direction(direction):
    """Validate the ``dir`` parameter (Req 11.7).

    Returns ``asc`` or ``desc``.  Falls back to the default direction when
    omitted; raises ``ValidationError`` (→ 400) for an unknown value.
    """
    if not direction:
        direction = DEFAULT_DIRECTION
    if direction not in SORT_DIRECTIONS:
        allowed = ", ".join(SORT_DIRECTIONS)
        raise ValidationError(
            {"detail": f"Invalid direction value '{direction}'. Allowed values: {allowed}."}
        )
    return direction
