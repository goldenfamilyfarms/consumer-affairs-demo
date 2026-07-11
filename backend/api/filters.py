"""Query-parameter validation for the brand listing endpoint (Ninja version).

Validation runs before the queryset is built so every invalid value produces a
clean ``400`` with a ``{"detail": "..."}`` body — Ninja renders ``HttpError``
that way, matching the DRF baseline's contract exactly.

The ``sort`` allowlist is decoupled from column names: the public value
(``avg_rating`` / ``review_count``) maps to the annotation from
``Brand.objects.with_stats()``.
"""

from ninja.errors import HttpError

from catalog.cache import get_industry_slugs

# Public sort value -> annotated field on Brand.objects.with_stats().
SORT_FIELDS = {
    "avg_rating": "computed_average_rating",
    "review_count": "review_count",
}
SORT_DIRECTIONS = ("asc", "desc")
DEFAULT_SORT = "avg_rating"
DEFAULT_DIRECTION = "desc"


def validate_industry(slug):
    """Return the slug if it names an existing industry, ``None`` if omitted.

    Unknown slug → 400 (checked against the cached slug set, not a per-request
    query).
    """
    if not slug:
        return None
    if slug not in get_industry_slugs():
        raise HttpError(400, f"Invalid filter value: no industry with slug '{slug}'.")
    return slug


def validate_sort(sort):
    """Return the annotated field to order by; unknown value → 400."""
    if not sort:
        sort = DEFAULT_SORT
    if sort not in SORT_FIELDS:
        allowed = ", ".join(sorted(SORT_FIELDS))
        raise HttpError(400, f"Invalid sort value '{sort}'. Allowed values: {allowed}.")
    return SORT_FIELDS[sort]


def validate_direction(direction):
    """Return ``asc``/``desc``; unknown value → 400."""
    if not direction:
        direction = DEFAULT_DIRECTION
    if direction not in SORT_DIRECTIONS:
        allowed = ", ".join(SORT_DIRECTIONS)
        raise HttpError(
            400, f"Invalid direction value '{direction}'. Allowed values: {allowed}."
        )
    return direction
