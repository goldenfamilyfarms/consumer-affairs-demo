"""Django Ninja API for the brand listing (alternative to the DRF baseline).

Exposes the same contract as the DRF version:

    GET /api/brands/      -> page-number envelope {count, next, previous, results}
    GET /api/industries/  -> [{name, slug, brand_count}, ...]

Same params (industry slug, sort, dir, page, page_size), same 400/404 semantics,
same card shape — so the React client and the (converted) test suite are
framework-agnostic. The difference is purely how the framework is wired:
declarative Pydantic schemas + plain functions instead of DRF viewsets.
"""

from __future__ import annotations

import math
from typing import List, Optional

from django.db.models import Count

from ninja import NinjaAPI, Query
from ninja.errors import HttpError

from api.filters import validate_direction, validate_industry, validate_sort
from api.queries import brand_card_queryset
from api.schemas import BrandPageSchema, IndustrySchema
from catalog.models import Industry

api = NinjaAPI(title="Brand Reviews API (Ninja)", urls_namespace="ninja")

DEFAULT_PAGE_SIZE = 12
MAX_PAGE_SIZE = 100


def _page_url(request, page_number: int, page_size: int) -> str:
    """Absolute URL for a given page, preserving the current query params."""
    params = request.GET.copy()
    params["page"] = str(page_number)
    params["page_size"] = str(page_size)
    return request.build_absolute_uri(f"{request.path}?{params.urlencode()}")


def _paginate(request, queryset, page: int, page_size: int) -> dict:
    """Page-number pagination matching the DRF baseline's envelope + semantics.

    - ``page_size`` is clamped to ``MAX_PAGE_SIZE`` (not rejected).
    - An out-of-range page raises 404 (DRF's default behaviour).
    - ``next``/``previous`` are absolute URLs, or ``None`` at the ends.
    """
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    count = queryset.count()
    total_pages = max(1, math.ceil(count / page_size))

    if page < 1 or page > total_pages:
        raise HttpError(404, "Invalid page.")

    start = (page - 1) * page_size
    results = list(queryset[start : start + page_size])

    return {
        "count": count,
        "next": _page_url(request, page + 1, page_size) if page < total_pages else None,
        "previous": _page_url(request, page - 1, page_size) if page > 1 else None,
        "results": results,
    }


@api.get("/brands/", response=BrandPageSchema)
def list_brands(
    request,
    industry: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE),
):
    """List brands with per-card stats, filtering, sorting, and pagination."""
    industry_slug = validate_industry(industry)
    sort_field = validate_sort(sort)
    direction = validate_direction(dir)

    queryset = brand_card_queryset(industry_slug, sort_field, direction)
    return _paginate(request, queryset, page, page_size)


@api.get("/industries/", response=List[IndustrySchema])
def list_industries(request):
    """List all industries (unpaginated) for the filter control."""
    return Industry.objects.annotate(brand_count=Count("brands")).order_by("name")
