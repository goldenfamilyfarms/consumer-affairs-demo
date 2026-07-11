"""Property-based tests for ``GET /api/brands/`` (Req 10, 11).

These Hypothesis tests assert the universal correctness properties against the
real endpoint via Django's test ``Client`` (framework-agnostic; passes against
DRF or Django Ninja).

Properties covered:

- Property 9  — Pagination invariants   (Req 11.1, 11.2, 11.3)
- Property 10 — Sort monotonicity        (Req 10.4, 10.5, 11.7)
- Property 11 — Filter soundness         (Req 10.3, 11.4)
- Property 8  — Top-review rule          (Req 10.6, 10.7)

Each test uses ``@pytest.mark.django_db(transaction=True)`` and resets the
relevant tables in a ``finally`` block so every Hypothesis example starts from
a clean database.
"""

from datetime import datetime, timedelta, timezone
from http import HTTPStatus

import pytest
from django.test import Client
from hypothesis import given, settings
from hypothesis import strategies as st

from api.queries import excerpt
from catalog.models import Brand, Industry, Review

BRANDS_URL = "/api/brands/"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _reset_tables():
    """Delete every row created by an example so the next one starts fresh."""
    Review.objects.all().delete()
    Brand.objects.all().delete()
    Industry.objects.all().delete()


def assert_nulls_last_monotonic(values, direction):
    """Assert *values* are sorted per *direction* with ``None`` values last."""
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
# Property 9: Pagination invariants
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@given(
    num_brands=st.integers(min_value=0, max_value=20),
    page_size=st.integers(min_value=1, max_value=12),
)
@settings(max_examples=30, deadline=None)
def test_property_pagination_invariants(num_brands, page_size):
    """**Validates: Requirements 11.1, 11.2, 11.3**"""
    client = Client()
    url = BRANDS_URL
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
            for j in range(i % 3):
                Review.objects.create(
                    title=f"Review {review_counter}",
                    slug=f"review-{review_counter}",
                    rating=(j % 5) + 1,
                    brand=brand,
                    wp_post_id=50000 + review_counter,
                )
                review_counter += 1

        full_resp = client.get(url, {"page_size": 100})
        assert full_resp.status_code == HTTPStatus.OK
        full_slugs = [row["slug"] for row in full_resp.json()["results"]]
        assert len(full_slugs) == num_brands

        collected = []
        page_num = 1
        while True:
            resp = client.get(url, {"page": page_num, "page_size": page_size})
            assert resp.status_code == HTTPStatus.OK
            body = resp.json()

            assert body["count"] == num_brands
            assert len(body["results"]) <= page_size

            collected.extend(row["slug"] for row in body["results"])

            if body["next"] is None:
                break
            page_num += 1

        assert collected == full_slugs
        assert len(collected) == len(set(collected))
    finally:
        _reset_tables()


# ---------------------------------------------------------------------------
# Property 10: Sort monotonicity
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
    """**Validates: Requirements 10.4, 10.5, 11.7**"""
    client = Client()
    url = BRANDS_URL
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
                assert resp.status_code == HTTPStatus.OK
                results = resp.json()["results"]
                assert len(results) == len(brands)
                values = [row[key] for row in results]
                assert_nulls_last_monotonic(values, direction)
    finally:
        _reset_tables()


# ---------------------------------------------------------------------------
# Property 11: Filter soundness
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@given(assignments=st.lists(st.integers(min_value=0, max_value=3), min_size=0, max_size=20))
@settings(max_examples=30, deadline=None)
def test_property_filter_soundness(assignments):
    """**Validates: Requirements 10.3, 11.4**"""
    client = Client()
    url = BRANDS_URL
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

        for idx in range(num_industries):
            slug = f"industry-{idx}"
            resp = client.get(url, {"industry": slug, "page_size": 100})
            assert resp.status_code == HTTPStatus.OK
            body = resp.json()
            returned = {row["slug"] for row in body["results"]}
            assert returned == industry_brands[idx], f"industry={slug}"
            assert body["count"] == len(industry_brands[idx])

        unknown_slug = "no-such-industry-xyz"
        assert unknown_slug not in {f"industry-{i}" for i in range(num_industries)}
        resp = client.get(url, {"industry": unknown_slug})
        assert resp.status_code == HTTPStatus.BAD_REQUEST
        assert "detail" in resp.json()
    finally:
        _reset_tables()


# ---------------------------------------------------------------------------
# Property 8: Top-review rule
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@given(ratings=st.lists(st.integers(min_value=0, max_value=5), min_size=0, max_size=12))
@settings(max_examples=40, deadline=None)
def test_property_top_review_rule(ratings):
    """**Validates: Requirements 10.6, 10.7**"""
    client = Client()
    url = BRANDS_URL
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
            date = base_date + timedelta(days=i)
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

        qualifying = [(r, d, b) for (r, d, b) in reviews if r >= 1]
        if not qualifying:
            expected_snippet = None
        else:
            top = max(qualifying, key=lambda t: (t[0], t[1]))
            expected_snippet = excerpt(top[2])

        resp = client.get(url)
        assert resp.status_code == HTTPStatus.OK
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["top_review_snippet"] == expected_snippet
    finally:
        _reset_tables()
