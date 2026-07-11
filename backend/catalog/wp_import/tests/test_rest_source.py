"""Unit + integration tests for :class:`RestApiSource`.

The REST source reads the live WordPress REST API, but these tests inject a
fake ``fetch_json`` returning canned payloads — so they run fully offline (no
WordPress stack) while proving the JSON→dataclass mapping and that the importer
runs unchanged against this third source (the payoff of the source protocol).
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from catalog.models import Brand, Industry, Review, Reviewer
from catalog.wp_import.importer import run_import
from catalog.wp_import.sources import RestApiSource, WordPressSource


def make_fetch(data: dict, per_page: int = 100):
    """Return a fake ``fetch_json(url)`` that slices canned data by page.

    ``data`` maps a REST resource (``brands``/``reviews``/``industry``/``users``)
    to its full list of items; the fake honours the ``page``/``per_page`` query
    params so pagination is exercised exactly like the real API.
    """

    def fetch(url: str):
        parsed = urlparse(url)
        resource = parsed.path.rsplit("/", 1)[-1]
        page = int(parse_qs(parsed.query).get("page", ["1"])[0])
        items = data.get(resource, [])
        start = (page - 1) * per_page
        return items[start : start + per_page]

    return fetch


# --------------------------------------------------------------------------- #
# Mapping
# --------------------------------------------------------------------------- #


def test_industries_mapping():
    data = {"industry": [{"id": 1, "name": "Insurance", "slug": "insurance"}]}
    source = RestApiSource(base_url="http://wp.test", fetch_json=make_fetch(data))

    industries = list(source.industries())

    assert len(industries) == 1
    assert (industries[0].wp_term_id, industries[0].name, industries[0].slug) == (
        1,
        "Insurance",
        "insurance",
    )


def test_brand_mapping_reads_rendered_acf_and_yoast():
    data = {
        "brands": [
            {
                "id": 10,
                "slug": "acme",
                "date": "2026-05-19T20:28:55",
                "title": {"rendered": "Acme"},
                "content": {"rendered": "<p>Acme body</p>"},
                "industry": [1],
                "acf": {
                    "website_url": "https://acme.example",
                    "founded_year": "1998",
                    "headquarters": "Austin, TX",
                    "average_rating": "4.25",
                },
                "yoast_head_json": {"title": "Acme | Best", "description": "Acme meta"},
            }
        ]
    }
    source = RestApiSource(base_url="http://wp.test", fetch_json=make_fetch(data))

    brand = next(iter(source.brands()))

    assert brand.wp_post_id == 10
    assert brand.name == "Acme"
    assert brand.slug == "acme"
    assert brand.body == "<p>Acme body</p>"  # HTML kept; sanitized at render time
    assert brand.industry_wp_term_id == 1
    assert brand.website_url == "https://acme.example"
    assert brand.founded_year == 1998
    assert brand.headquarters == "Austin, TX"
    assert brand.average_rating == Decimal("4.25")
    assert brand.seo_title == "Acme | Best"
    assert brand.seo_metadesc == "Acme meta"
    # ISO timestamp parsed to an aware datetime.
    assert brand.wp_post_date is not None
    assert brand.wp_post_date.tzinfo is not None
    assert (brand.wp_post_date.year, brand.wp_post_date.month) == (2026, 5)


@pytest.mark.parametrize(
    "brand_ref, expected",
    [
        (10, 10),               # bare id
        ("10", 10),             # numeric string
        ({"ID": 10}, 10),       # ACF post-object (WP-style key)
        ({"id": 10}, 10),       # ACF post-object (lowercase)
        (None, None),           # unset
    ],
)
def test_review_brand_reference_normalization(brand_ref, expected):
    data = {
        "reviews": [
            {
                "id": 20,
                "slug": "great",
                "date": "2026-05-19T20:28:55",
                "title": {"rendered": "Great"},
                "content": {"rendered": "Loved it"},
                "author": 7,
                "acf": {
                    "rating": "5",
                    "reviewer_name": "Jane Doe",
                    "reviewer_location": "Denver, CO",
                    "brand": brand_ref,
                },
            }
        ]
    }
    source = RestApiSource(base_url="http://wp.test", fetch_json=make_fetch(data))

    review = next(iter(source.reviews()))

    assert review.wp_post_id == 20
    assert review.title == "Great"
    assert review.rating == 5
    assert review.reviewer_name == "Jane Doe"
    assert review.reviewer_location == "Denver, CO"
    assert review.wp_user_id == 7
    assert review.brand_wp_post_id == expected


def test_users_mapping_falls_back_to_slug_and_name():
    data = {"users": [{"id": 7, "name": "Jane Doe", "slug": "jane"}]}
    source = RestApiSource(base_url="http://wp.test", fetch_json=make_fetch(data))

    user = next(iter(source.users()))

    assert user.wp_user_id == 7
    assert user.display_name == "Jane Doe"
    assert user.user_login == "jane"
    assert user.email == ""  # REST omits email by default


# --------------------------------------------------------------------------- #
# Pagination
# --------------------------------------------------------------------------- #


def test_pagination_walks_all_pages():
    terms = [{"id": i, "name": f"I{i}", "slug": f"i-{i}"} for i in range(1, 6)]  # 5 items
    source = RestApiSource(
        base_url="http://wp.test", per_page=2, fetch_json=make_fetch({"industry": terms}, per_page=2)
    )

    got = [i.wp_term_id for i in source.industries()]

    assert got == [1, 2, 3, 4, 5]  # 3 pages (2 + 2 + 1) all followed


def test_error_object_ends_the_walk():
    # WP returns a dict (error) instead of a list once the page is out of range.
    def fetch(url):
        # Parse the real `page` query param — a naive substring check would
        # collide with "per_page=1".
        page = int(parse_qs(urlparse(url).query).get("page", ["1"])[0])
        if page == 1:
            return [{"id": 1, "name": "Insurance", "slug": "insurance"}]
        return {"code": "rest_post_invalid_page_number", "message": "out of range"}

    source = RestApiSource(base_url="http://wp.test", per_page=1, fetch_json=fetch)
    got = [i.wp_term_id for i in source.industries()]

    assert got == [1]  # non-list response terminated the walk cleanly


# --------------------------------------------------------------------------- #
# Protocol conformance + importer integration
# --------------------------------------------------------------------------- #


def test_conforms_to_wordpress_source_protocol():
    source = RestApiSource(base_url="http://wp.test", fetch_json=make_fetch({}))
    assert isinstance(source, WordPressSource)


@pytest.mark.django_db
def test_importer_runs_unchanged_against_rest_source():
    """The same run_import() imports REST-sourced data with no importer change."""
    data = {
        "industry": [{"id": 1, "name": "Insurance", "slug": "insurance"}],
        "users": [
            {"id": 2, "name": "Jane", "slug": "jane"},
            {"id": 3, "name": "Sam", "slug": "sam"},
            {"id": 99, "name": "Admin", "slug": "admin"},  # not a review author
        ],
        "brands": [
            {
                "id": 10, "slug": "acme", "date": "2026-01-01T00:00:00",
                "title": {"rendered": "Acme"}, "content": {"rendered": "b"},
                "industry": [1], "acf": {"average_rating": "4.0"},
            },
            {
                "id": 11, "slug": "beta", "date": "2026-01-02T00:00:00",
                "title": {"rendered": "Beta"}, "content": {"rendered": "b"},
                "industry": [1], "acf": {},
            },
        ],
        "reviews": [
            {
                "id": 20, "slug": "r1", "date": "2026-02-01T00:00:00",
                "title": {"rendered": "R1"}, "content": {"rendered": "x"},
                "author": 2, "acf": {"rating": "5", "brand": 10},
            },
            {
                "id": 21, "slug": "r2", "date": "2026-02-02T00:00:00",
                "title": {"rendered": "R2"}, "content": {"rendered": "y"},
                "author": 3, "acf": {"rating": "4", "brand": {"ID": 11}},
            },
        ],
    }
    source = RestApiSource(base_url="http://wp.test", fetch_json=make_fetch(data))

    summary = run_import(source)

    assert Industry.objects.count() == 1
    # Only users referenced as review authors become reviewers (2 & 3, not 99).
    assert Reviewer.objects.count() == 2
    assert Brand.objects.count() == 2
    assert Review.objects.count() == 2
    assert summary.reviews_created == 2
    # Re-run is idempotent even from the REST source.
    summary2 = run_import(RestApiSource(base_url="http://wp.test", fetch_json=make_fetch(data)))
    assert (summary2.brands_created, summary2.reviews_created) == (0, 0)
    assert (summary2.brands_updated, summary2.reviews_updated) == (0, 0)
