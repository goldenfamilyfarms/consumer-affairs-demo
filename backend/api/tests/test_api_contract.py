"""Example-based contract tests for ``GET /api/brands/`` (Req 10, 11).

These tests pin the concrete API contract with specific, hand-built datasets:

- the response envelope shape and every serialized card field,
- filtering by each industry slug,
- both sort keys (``avg_rating`` / ``review_count``) in both directions,
- the default page size and an explicit ``page_size`` override,
- 400 responses for an unknown industry / invalid sort / invalid dir,
- a 404 for a page number beyond the available range,
- the zero-review brand row shape.

They complement the Hypothesis property tests (which assert the same
invariants universally) with readable, deterministic examples.

Testing framework: pytest + pytest-django with DRF's ``APIClient``.
"""

from datetime import datetime, timezone

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from catalog.models import Brand, Industry, Review


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# The full set of serializer fields every card row must carry (Req 10.2).
CARD_FIELDS = {
    "name",
    "slug",
    "industry",
    "industry_slug",
    "average_rating",
    "review_count",
    "short_description",
    "top_review_snippet",
}

# The pagination envelope keys every list response must carry (Req 11.1).
ENVELOPE_KEYS = {"count", "next", "previous", "results"}


@pytest.fixture
def client():
    """A DRF test client for issuing API requests."""
    return APIClient()


@pytest.fixture
def list_url():
    """The reversed URL for the brand listing endpoint (Req 10.1)."""
    return reverse("api:brand-list")


class DataFactory:
    """Builds Industry/Brand/Review rows with unique natural keys.

    Keeps a running counter so ``wp_*_id`` and slug values never collide
    across the objects created within a single test.
    """

    def __init__(self):
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def industry(self, name: str, slug: str) -> Industry:
        return Industry.objects.create(
            name=name, slug=slug, wp_term_id=self._next()
        )

    def brand(self, name: str, slug: str, industry: Industry, body: str = "") -> Brand:
        return Brand.objects.create(
            name=name,
            slug=slug,
            body=body,
            industry=industry,
            wp_post_id=1000 + self._next(),
        )

    def review(
        self,
        brand: Brand,
        rating: int,
        body: str = "A perfectly ordinary review body.",
        wp_post_date: datetime | None = None,
    ) -> Review:
        n = self._next()
        return Review.objects.create(
            title=f"Review {n}",
            slug=f"review-{n}",
            body=body,
            rating=rating,
            brand=brand,
            wp_post_id=5000 + n,
            wp_post_date=wp_post_date,
        )

    def brand_with_reviews(
        self, name: str, slug: str, industry: Industry, ratings: list[int]
    ) -> Brand:
        """Create a brand and attach one review per rating in *ratings*."""
        brand = self.brand(name=name, slug=slug, industry=industry)
        for rating in ratings:
            self.review(brand, rating=rating)
        return brand


@pytest.fixture
def factory():
    return DataFactory()


def assert_nulls_last_monotonic(values, direction):
    """Assert *values* are sorted per *direction* with ``None`` values last.

    Non-null values must appear before any null, and the non-null prefix must
    be non-decreasing (``asc``) or non-increasing (``desc``).
    """
    # All nulls must be at the tail (Req 10.4/10.5 nulls-last rule).
    seen_null = False
    for v in values:
        if v is None:
            seen_null = True
        else:
            assert not seen_null, f"non-null {v} appeared after a null in {values}"

    non_null = [v for v in values if v is not None]
    if direction == "asc":
        assert non_null == sorted(non_null), f"{non_null} not ascending"
    else:
        assert non_null == sorted(non_null, reverse=True), f"{non_null} not descending"


# ---------------------------------------------------------------------------
# Response contract shape (Req 10.1, 10.2, 11.1)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_response_envelope_and_card_field_shape(client, list_url, factory):
    """**Validates: Requirements 10.1, 10.2, 11.1**

    A basic ``GET /api/brands/`` returns 200 with the ``count``/``next``/
    ``previous``/``results`` envelope, and every result row carries exactly
    the documented card fields.
    """
    industry = factory.industry("Insurance", "insurance")
    factory.brand_with_reviews("Acme", "acme", industry, ratings=[5, 4, 3])

    response = client.get(list_url)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()

    # Envelope shape (Req 11.1).
    assert set(body.keys()) == ENVELOPE_KEYS
    assert body["count"] == 1
    assert body["previous"] is None
    assert isinstance(body["results"], list)

    # Card field shape (Req 10.2) — exactly the documented fields, no more.
    row = body["results"][0]
    assert set(row.keys()) == CARD_FIELDS
    assert row["name"] == "Acme"
    assert row["slug"] == "acme"
    assert row["industry"] == "Insurance"  # industry name string
    assert row["industry_slug"] == "insurance"  # slug the filter round-trips on
    assert row["average_rating"] == 4.0  # mean of 5,4,3
    assert row["review_count"] == 3
    assert isinstance(row["top_review_snippet"], str)


# ---------------------------------------------------------------------------
# Filtering by industry slug (Req 10.3, 11.4)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_filter_by_each_industry_slug_returns_only_that_industry(
    client, list_url, factory
):
    """**Validates: Requirements 10.3**

    Filtering by each industry slug returns only the brands belonging to that
    industry, and never brands from other industries.
    """
    insurance = factory.industry("Insurance", "insurance")
    banking = factory.industry("Banking", "banking")
    autos = factory.industry("Autos", "autos")

    factory.brand_with_reviews("Acme Insurance", "acme-ins", insurance, [5, 4])
    factory.brand_with_reviews("Beta Insurance", "beta-ins", insurance, [3])
    factory.brand_with_reviews("Cash Bank", "cash-bank", banking, [2, 2])
    factory.brand_with_reviews("Drive Autos", "drive-autos", autos, [4])

    expected = {
        "insurance": {"acme-ins", "beta-ins"},
        "banking": {"cash-bank"},
        "autos": {"drive-autos"},
    }

    for slug, expected_slugs in expected.items():
        response = client.get(list_url, {"industry": slug})
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        returned_slugs = {row["slug"] for row in body["results"]}
        assert returned_slugs == expected_slugs, f"industry={slug}"
        assert body["count"] == len(expected_slugs)


# ---------------------------------------------------------------------------
# Sorting: both keys x both directions (Req 10.4, 10.5, 11.7)
# ---------------------------------------------------------------------------


@pytest.fixture
def sortable_dataset(factory):
    """Build brands with distinct average ratings and review counts.

    Includes a zero-review brand so the nulls-last rule is exercised.
    """
    industry = factory.industry("Insurance", "insurance")
    # avg 5.0, count 2
    factory.brand_with_reviews("High", "high", industry, [5, 5])
    # avg 3.0, count 3
    factory.brand_with_reviews("Mid", "mid", industry, [3, 3, 3])
    # avg 4.0, count 1
    factory.brand_with_reviews("One", "one", industry, [4])
    # zero reviews -> avg null, count 0
    factory.brand("Empty", "empty", industry)
    return industry


@pytest.mark.django_db
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_by_avg_rating_both_directions(
    client, list_url, sortable_dataset, direction
):
    """**Validates: Requirements 10.4, 11.7**

    ``sort=avg_rating`` orders rows by computed average rating in the given
    direction, with null averages last.
    """
    response = client.get(
        list_url, {"sort": "avg_rating", "dir": direction, "page_size": 100}
    )
    assert response.status_code == status.HTTP_200_OK
    ratings = [row["average_rating"] for row in response.json()["results"]]
    assert_nulls_last_monotonic(ratings, direction)
    # The zero-review brand's null average must be present and last.
    assert ratings[-1] is None


@pytest.mark.django_db
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_by_review_count_both_directions(
    client, list_url, sortable_dataset, direction
):
    """**Validates: Requirements 10.5, 11.7**

    ``sort=review_count`` orders rows by review count in the given direction.
    """
    response = client.get(
        list_url, {"sort": "review_count", "dir": direction, "page_size": 100}
    )
    assert response.status_code == status.HTTP_200_OK
    counts = [row["review_count"] for row in response.json()["results"]]
    assert_nulls_last_monotonic(counts, direction)


# ---------------------------------------------------------------------------
# Pagination: default and explicit page sizes (Req 11.2, 11.3)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_default_page_size_is_twelve(client, list_url, factory):
    """**Validates: Requirements 11.3**

    Omitting ``page_size`` applies the default page size of 12: a first page
    returns 12 rows and a ``next`` link while ``count`` reflects the total.
    """
    industry = factory.industry("Insurance", "insurance")
    for i in range(15):
        factory.brand_with_reviews(f"Brand {i}", f"brand-{i}", industry, [4])

    response = client.get(list_url)
    assert response.status_code == status.HTTP_200_OK
    body = response.json()

    assert body["count"] == 15
    assert len(body["results"]) == 12
    assert body["next"] is not None
    assert body["previous"] is None


@pytest.mark.django_db
def test_explicit_page_size_override(client, list_url, factory):
    """**Validates: Requirements 11.2**

    An explicit ``page_size`` controls the number of rows per page.
    """
    industry = factory.industry("Insurance", "insurance")
    for i in range(15):
        factory.brand_with_reviews(f"Brand {i}", f"brand-{i}", industry, [4])

    response = client.get(list_url, {"page_size": 5})
    assert response.status_code == status.HTTP_200_OK
    body = response.json()

    assert body["count"] == 15
    assert len(body["results"]) == 5
    assert body["next"] is not None


# ---------------------------------------------------------------------------
# 400 responses for bad parameters (Req 11.4, 11.5)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unknown_industry_returns_400(client, list_url, factory):
    """**Validates: Requirements 11.4**

    An unknown industry filter yields 400 with a ``detail`` message, never an
    empty 200.
    """
    factory.industry("Insurance", "insurance")

    response = client.get(list_url, {"industry": "does-not-exist"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in response.json()


@pytest.mark.django_db
def test_invalid_sort_returns_400(client, list_url, factory):
    """**Validates: Requirements 11.5**

    An invalid ``sort`` value yields 400 with a ``detail`` message.
    """
    industry = factory.industry("Insurance", "insurance")
    factory.brand_with_reviews("Acme", "acme", industry, [4])

    response = client.get(list_url, {"sort": "not_a_field"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in response.json()


@pytest.mark.django_db
def test_invalid_direction_returns_400(client, list_url, factory):
    """**Validates: Requirements 11.5**

    An invalid ``dir`` value yields 400 with a ``detail`` message.
    """
    industry = factory.industry("Insurance", "insurance")
    factory.brand_with_reviews("Acme", "acme", industry, [4])

    response = client.get(list_url, {"sort": "avg_rating", "dir": "sideways"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# 404 for out-of-range page (Req 11.6)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_page_beyond_range_returns_404(client, list_url, factory):
    """**Validates: Requirements 11.6**

    Requesting a page number beyond the available range yields 404.
    """
    industry = factory.industry("Insurance", "insurance")
    factory.brand_with_reviews("Acme", "acme", industry, [4])

    # Only one row exists, so page 2 is out of range.
    response = client.get(list_url, {"page": 2})
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Zero-review brand row shape (Req 10.7)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_zero_review_brand_row_shape(client, list_url, factory):
    """**Validates: Requirements 10.7**

    A brand with no qualifying reviews returns ``review_count`` 0,
    ``average_rating`` null, and ``top_review_snippet`` null.
    """
    industry = factory.industry("Insurance", "insurance")
    factory.brand("Empty Co", "empty-co", industry, body="A brand with no reviews yet.")

    response = client.get(list_url, {"industry": "insurance"})
    assert response.status_code == status.HTTP_200_OK
    body = response.json()

    assert body["count"] == 1
    row = body["results"][0]
    assert row["slug"] == "empty-co"
    assert row["review_count"] == 0
    assert row["average_rating"] is None
    assert row["top_review_snippet"] is None


@pytest.mark.django_db
def test_zero_rating_reviews_do_not_qualify(client, list_url, factory):
    """**Validates: Requirements 10.7**

    A brand whose only reviews have ratings below 1 is treated as having zero
    qualifying reviews: count 0, null average, null snippet.
    """
    industry = factory.industry("Insurance", "insurance")
    brand = factory.brand("Zeroes", "zeroes", industry)
    factory.review(brand, rating=0)
    factory.review(brand, rating=0)

    response = client.get(list_url, {"industry": "insurance"})
    assert response.status_code == status.HTTP_200_OK
    row = response.json()["results"][0]

    assert row["review_count"] == 0
    assert row["average_rating"] is None
    assert row["top_review_snippet"] is None
