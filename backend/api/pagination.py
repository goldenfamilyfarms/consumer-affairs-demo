"""Pagination for the REST API.

Page-number pagination (Req 11.1-11.3): responses carry ``count``, ``next``,
``previous``, and ``results``.  ``next``/``previous`` are absolute URLs so a
mobile client can follow them without reconstructing query strings.

An out-of-range ``page`` yields DRF's default ``404`` (Req 11.6) — we keep that
behaviour intentionally rather than clamping to the last page.
"""

from rest_framework.pagination import PageNumberPagination


class BrandPagination(PageNumberPagination):
    """Page-number pagination for the brand listing endpoint.

    - Default page size is 12 (Req 11.3); ``PAGE_SIZE`` in settings supplies the
      same default, and this explicit value keeps the contract self-documenting.
    - ``page`` selects the page (Req 11.2); ``page_size`` overrides the row count
      per page (Req 11.2).
    - ``page_size`` is bounded by ``max_page_size`` (100): a request above the
      cap is **clamped** to 100 (DRF's standard behaviour) rather than rejected,
      so clients get a valid — if smaller-than-asked — page instead of a 400.
      The cap and default are documented in the README's "API endpoints"
      section. (If a hard error were preferred, we'd override ``get_page_size``
      to raise a ``ValidationError`` when the requested size exceeds the cap.)
    """

    page_size = 12
    page_query_param = "page"
    page_size_query_param = "page_size"
    max_page_size = 100
