"""REST API views.

``BrandListView`` backs ``GET /api/brands/`` (Req 10, 11).  It lists brands with
their computed stats, supports filtering by industry slug and sorting by average
rating or review count in either direction, and paginates the result.

Efficiency: the queryset annotates stats in the database (``with_stats``),
prefetches each brand's top review (``top_review_prefetch``), and selects the
related industry so serializing a page never triggers an N+1 query.
"""

from django.db.models import Count, F

from rest_framework.generics import ListAPIView

from catalog.models import Brand, Industry

from api.filters import (
    validate_direction,
    validate_industry,
    validate_sort,
)
from api.pagination import BrandPagination
from api.serializers import (
    BrandCardSerializer,
    IndustrySerializer,
    top_review_prefetch,
)


class BrandListView(ListAPIView):
    """List brands with per-card stats, filtering, sorting, and pagination.

    Query parameters (all optional):

    - ``industry``: filter to a single industry by slug; unknown → 400.
    - ``sort``: ``avg_rating`` | ``review_count``; invalid → 400.
    - ``dir``: ``asc`` | ``desc``; invalid → 400.
    - ``page`` / ``page_size``: pagination controls; page out of range → 404.
    """

    serializer_class = BrandCardSerializer
    pagination_class = BrandPagination

    def get_queryset(self):
        """Build the validated, filtered, and ordered brand queryset.

        Validation runs first (before any DB work) so an invalid parameter
        returns a clean 400 (Req 10.3-10.5, 11.4, 11.5, 11.7).
        """
        params = self.request.query_params

        industry_slug = validate_industry(params.get("industry"))
        sort_field = validate_sort(params.get("sort"))
        direction = validate_direction(params.get("dir"))

        queryset = (
            Brand.objects.with_stats()
            .select_related("industry")
            .prefetch_related(top_review_prefetch())
        )

        if industry_slug:
            queryset = queryset.filter(industry__slug=industry_slug)

        # Sort on the DB annotation. Null average ratings always sort last,
        # regardless of direction, so brands without a rating never crowd the
        # top of a descending list nor the top of an ascending one.
        order = F(sort_field)
        if direction == "asc":
            ordering = order.asc(nulls_last=True)
        else:
            ordering = order.desc(nulls_last=True)

        # Stable tiebreak by slug keeps pagination deterministic across pages.
        return queryset.order_by(ordering, "slug")


class IndustryListView(ListAPIView):
    """List all industries for the filter control (``GET /api/industries/``).

    Unpaginated — the set is small and bounded, and the client wants the whole
    list at once to populate a dropdown. Each row carries a ``brand_count`` so a
    consumer can show counts or hide empty industries without a second call.
    """

    serializer_class = IndustrySerializer
    pagination_class = None

    def get_queryset(self):
        return Industry.objects.annotate(brand_count=Count("brands")).order_by("name")
