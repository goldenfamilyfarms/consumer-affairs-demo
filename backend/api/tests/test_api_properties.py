"""Property-based tests for ``GET /api/brands/`` (Req 10, 11).

These Hypothesis tests assert the universal correctness properties from the
design document against the real endpoint. Each test builds a generated
brand/review dataset, drives DRF's ``APIClient`` against ``/api/brands/``, and
verifies the invariant holds for every generated example.

Properties covered:

- Property 9  — Pagination invariants   (Req 11.1, 11.2, 11.3)
- Property 10 — Sort monotonicity        (Req 10.4, 10.5, 11.7)
- Property 11 — Filter soundness         (Req 10.3, 11.4)
- Property 8  — Top-review rule          (Req 10.6, 10.7)

Testing framework: Hypothesis + pytest-django with DRF's ``APIClient``.

Each test uses ``@pytest.mark.django_db(transaction=True)`` and resets the
relevant tables in a ``finally`` block so every Hypothesis example starts from
a clean database. Natural keys (``wp_*_id``) and slugs are kept unique within
each generated example.
"""

from datetime import datetime, timedelta, timezone

import pytest
from django.urls import reverse
from hypothesis import given, settings
from hypothesis import strategies as st
from rest_framework import status
from rest_framework.test import APIClient

from api.serializers import excerpt
from catalog.models import Brand, Industry, Review


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _reset_tables():
    """Delete every row created by an example so the next one starts fresh.

    Order matters: reviews and brands reference industries, so remove them
    first. Called from a ``finally`` block in each property test.
    """
    Review.objects.all().delete()
    Brand.objects.all().delete()
    Industry.objects.all().delete()


def _list_url():
    """The reversed URL for the brand listing endpoint (Req 10.1)."""
    return reverse("api:brand-list")


def assert_nulls_last_monotonic(values, direction):
    """Assert *values* are sorted per *direction* with ``None`` values last.

    Non-null values must all appear before any null, and the non-null prefix
    must be non-decreasing (``asc``) or non-increasing (``desc``). Mirrors the
    nulls-last ordering rule the view applies (Req 10.4/10.5).
    """
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
# Property 9: Pagination invariants (Task 7.3)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@given(
    num_brands=st.integers(min_value=0, max_value=20),
    page_size=st.integers(min_value=1, max_value=12),
)
@settings(max_examples=30, deadline=None)
def test_property_pagination_invariants(num_brands, page_size):
    """**Validates: Requirements 11.1, 11.2, 11.3**

    For any brand set paged with any ``page_size``:

    - every page returns at most ``page_size`` rows,
    - ``count`` equals the total matching rows on every page (independent of
      which page is requested), and
    - concatenating all pages reproduces the full ordered result set with no
      duplicates and no gaps.
    """
    client = APIClient()
    url = _list_url()
    try:
        industry = Industry.objects.create(
            name="Insurance", slug="insurance", wp_term_id=1
        )
        review_counter = 0
        for i in range(num_brands):
            brand = Brand.objects.create(
                name=f"Brand {i}",
                slug=f"brand-{i}",
                industry=industry,
                wp_post_id=1000 + i,
            )
            # Attach a varying number of qualifying reviews for realism so the
            # default sort (avg_rating) has ties and distinct values to order.
            for j in range(i % 3):
                Review.objects.create(
                    title=f"Review {review_counter}",
                    slug=f"review-{review_counter}",
                    rating=(j % 5) + 1,
                    brand=brand,
                    wp_post_id=50000 + review_counter,
                )
                review_counter += 1

        # The full ordered result set via a single large page. The endpoint
        # applies the same ordering regardless of page size, so this is the
        # ground truth the paged concatenation must reproduce.
        full_resp = client.get(url, {"page_size": 100})
        assert full_resp.status_code == status.HTTP_200_OK
        full_slugs = [row["slug"] for row in full_resp.json()["results"]]
        assert len(full_slugs) == num_brands

        # Page through the full set following the ``next`` link.
        collected = []
        page_num = 1
        while True:
            resp = client.get(url, {"page": page_num, "page_size": page_size})
            assert resp.status_code == status.HTTP_200_OK
            body = resp.json()

            # count is total matching rows, independent of the page (Req 11.1).
            assert body["count"] == num_brands
            # Never more than page_size rows on a page (Req 11.2, 11.3).
            assert len(body["results"]) <= page_size

            collected.extend(row["slug"] for row in body["results"])

            if body["next"] is None:
                break
            page_num += 1

        # Concatenation reproduces the full ordered set: same order, no gaps.
        assert collected == full_slugs
        # No duplicates across pages.
        assert len(collected) == len(set(collected))
    finally:
        _reset_tables()


# ---------------------------------------------------------------------------
# Property 10: Sort monotonicity (Task 7.4)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@given(
    brands=st.lists(
        st.lists(st.integers(min_value=0, max_value=5), max_size=8),
        min_size=0,
        max_size=12,
    )
)
@settings(max_examples=30, deadline=None)
def test_property_sort_monotonicity(brands):
    """**Validates: Requirements 10.4, 10.5, 11.7**

    For ``sort=avg_rating`` / ``review_count`` in either direction, the full
    result set is non-decreasing (``asc``) or non-increasing (``desc``) on the
    sort key, with null average ratings ordered last.

    ``brands`` is a list of rating lists — one entry per brand — so the dataset
    includes empty-review brands (null average) and ratings spanning 0..5.
    """
    client = APIClient()
    url = _list_url()
    try:
        industry = Industry.objects.create(
            name="Insurance", slug="insurance", wp_term_id=1
        )
        review_counter = 0
        for i, ratings in enumerate(brands):
            brand = Brand.objects.create(
                name=f"Brand {i}",
                slug=f"brand-{i}",
                industry=industry,
                wp_post_id=2000 + i,
            )
            for rating in ratings:
                Review.objects.create(
                    title=f"Review {review_counter}",
                    slug=f"review-{review_counter}",
                    rating=rating,
                    brand=brand,
                    wp_post_id=60000 + review_counter,
                )
                review_counter += 1

        for sort, key in (("avg_rating", "average_rating"), ("review_count", "review_count")):
            for direction in ("asc", "desc"):
                resp = client.get(
                    url, {"sort": sort, "dir": direction, "page_size": 100}
                )
                assert resp.status_code == status.HTTP_200_OK
                results = resp.json()["results"]
                assert len(results) == len(brands)
                values = [row[key] for row in results]
                assert_nulls_last_monotonic(values, direction)
    finally:
        _reset_tables()


# ---------------------------------------------------------------------------
# Property 11: Filter soundness (Task 7.5)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@given(assignments=st.lists(st.integers(min_value=0, max_value=3), min_size=0, max_size=20))
@settings(max_examples=30, deadline=None)
def test_property_filter_soundness(assignments):
    """**Validates: Requirements 10.3, 11.4**

    Filtering by a valid industry slug returns exactly the brands belonging to
    that industry (every returned row belongs to it). An unknown industry slug
    yields a 400 — never an empty 200.

    ``assignments`` maps each generated brand to one of four industries; some
    industries may receive zero brands, which is a valid (empty) 200 filter.
    """
    client = APIClient()
    url = _list_url()
    num_industries = 4
    try:
        industries = {
            idx: Industry.objects.create(
                name=f"Industry {idx}", slug=f"industry-{idx}", wp_term_id=idx + 1
            )
            for idx in range(num_industries)
        }
        industry_brands = {idx: set() for idx in range(num_industries)}
        for k, idx in enumerate(assignments):
            Brand.objects.create(
                name=f"Brand {k}",
                slug=f"brand-{k}",
                industry=industries[idx],
                wp_post_id=3000 + k,
            )
            industry_brands[idx].add(f"brand-{k}")

        # Filter soundness: each valid slug returns exactly its own brands.
        for idx in range(num_industries):
            slug = f"industry-{idx}"
            resp = client.get(url, {"industry": slug, "page_size": 100})
            assert resp.status_code == status.HTTP_200_OK
            body = resp.json()
            returned = {row["slug"] for row in body["results"]}
            # Every returned row belongs to the requested industry, and no
            # brand of that industry is missing (Req 10.3).
            assert returned == industry_brands[idx], f"industry={slug}"
            assert body["count"] == len(industry_brands[idx])

        # An unknown slug must be a 400 with a detail message, not an empty 200.
        unknown_slug = "no-such-industry-xyz"
        assert unknown_slug not in {f"industry-{i}" for i in range(num_industries)}
        resp = client.get(url, {"industry": unknown_slug})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "detail" in resp.json()
    finally:
        _reset_tables()


# ---------------------------------------------------------------------------
# Property 8: Top-review rule (Task 7.6)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@given(ratings=st.lists(st.integers(min_value=0, max_value=5), min_size=0, max_size=12))
@settings(max_examples=40, deadline=None)
def test_property_top_review_rule(ratings):
    """**Validates: Requirements 10.6, 10.7**

    For a brand with at least one qualifying review (``rating >= 1``), the
    ``top_review_snippet`` corresponds to the review with the maximum rating,
    ties broken by the latest ``wp_post_date``. A brand with zero qualifying
    reviews yields a null snippet.

    Each review is given a distinct ``wp_post_date`` and a distinct, short body
    (< 160 chars, so the excerpt equals the body) so the expected top review is
    unambiguous and identifiable from the returned snippet.
    """
    client = APIClient()
    url = _list_url()
    base_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
    try:
        industry = Industry.objects.create(
            name="Insurance", slug="insurance", wp_term_id=1
        )
        brand = Brand.objects.create(
            name="Brand Top",
            slug="brand-top",
            industry=industry,
            wp_post_id=4000,
        )

        reviews = []  # (rating, date, body)
        for i, rating in enumerate(ratings):
            date = base_date + timedelta(days=i)  # distinct per review
            body = f"Review body number {i} with distinct content."
            Review.objects.create(
                title=f"Review {i}",
                slug=f"review-top-{i}",
                body=body,
                rating=rating,
                brand=brand,
                wp_post_id=70000 + i,
                wp_post_date=date,
            )
            reviews.append((rating, date, body))

        # Expected top review: highest qualifying rating, ties by latest date.
        qualifying = [(r, d, b) for (r, d, b) in reviews if r >= 1]
        if not qualifying:
            expected_snippet = None
        else:
            top = max(qualifying, key=lambda t: (t[0], t[1]))
            expected_snippet = excerpt(top[2])

        resp = client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["top_review_snippet"] == expected_snippet
    finally:
        _reset_tables()
