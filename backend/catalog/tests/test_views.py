"""Tests for the server-rendered catalog views.

Exercises the homepage, brand detail, and review detail pages through the
Django test client, asserting HTTP status, permalink resolution, required
field rendering, ordering, and 404 handling.

Covers Requirements 6.1, 6.2, 6.4, 6.5 (home), 7.1, 7.2, 7.4 (brand detail),
8.1, 8.2, 8.4 (review detail), and 9.3, 9.4 (permalink paths).

Testing framework: pytest + pytest-django with the Django test client.
"""

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest
from django.urls import reverse

from catalog.models import Brand, Industry, Review

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

# Monotonic counters guarantee unique WordPress natural keys and slugs across
# every object created in a test, mirroring the unique constraints on the
# models without hard-coding ids.
_wp_id = count(1000)
_slug_id = count(1)

# A fixed base instant so review ordering is deterministic and unambiguous.
_BASE_DATE = datetime(2020, 1, 1, tzinfo=timezone.utc)


def make_industry(name="Streaming", slug=None):
    return Industry.objects.create(
        name=name,
        slug=slug or f"industry-{next(_slug_id)}",
        wp_term_id=next(_wp_id),
    )


def make_brand(
    industry=None,
    name="Acme Streaming",
    slug=None,
    body="Acme has been streaming since day one.",
    website_url="https://acme.example.com",
    founded_year=1999,
    headquarters="Seattle, WA",
):
    return Brand.objects.create(
        name=name,
        slug=slug or f"brand-{next(_slug_id)}",
        body=body,
        website_url=website_url,
        founded_year=founded_year,
        headquarters=headquarters,
        industry=industry or make_industry(),
        wp_post_id=next(_wp_id),
    )


def make_review(
    brand=None,
    title="A great experience",
    slug=None,
    rating=5,
    reviewer_name="Jane Doe",
    reviewer_location="Portland, OR",
    body="I really enjoyed using this brand's service.",
    days_offset=0,
):
    return Review.objects.create(
        title=title,
        slug=slug or f"review-{next(_slug_id)}",
        rating=rating,
        reviewer_name=reviewer_name,
        reviewer_location=reviewer_location,
        body=body,
        brand=brand or make_brand(),
        wp_post_id=next(_wp_id),
        wp_post_date=_BASE_DATE + timedelta(days=days_offset),
    )


# ---------------------------------------------------------------------------
# Permalink resolution (Req 9.3, 9.4)
# ---------------------------------------------------------------------------


def test_permalink_paths_resolve():
    """Named routes resolve to the WordPress-compatible permalink paths.

    Requirements: 9.3 (/brand/<slug>/), 9.4 (/review/<slug>/), plus home.
    """
    assert reverse("catalog:home") == "/"
    assert reverse("catalog:brand_detail", args=["acme"]) == "/brand/acme/"
    assert reverse("catalog:review_detail", args=["great-review"]) == "/review/great-review/"


# ---------------------------------------------------------------------------
# Homepage (Req 6.1, 6.2, 6.4, 6.5)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_home_returns_200_and_renders_hero(client):
    """Home responds 200 and renders the hero section (Req 6.1)."""
    response = client.get(reverse("catalog:home"))

    assert response.status_code == 200
    content = response.content.decode()
    # The hero region and its headline copy from the theme.
    assert 'class="hero"' in content
    assert "Trusted Brand Reviews" in content


@pytest.mark.django_db
def test_home_shows_recent_reviews_most_recent_first(client):
    """Recent reviews are listed ordered by date descending (Req 6.2, 6.4).

    Also verifies each review links to its permalink (/review/<slug>/).
    """
    brand = make_brand()
    oldest = make_review(
        brand=brand, title="Oldest Review", slug="oldest-review", days_offset=0
    )
    middle = make_review(
        brand=brand, title="Middle Review", slug="middle-review", days_offset=5
    )
    newest = make_review(
        brand=brand, title="Newest Review", slug="newest-review", days_offset=10
    )

    response = client.get(reverse("catalog:home"))
    assert response.status_code == 200
    content = response.content.decode()

    # All three titles appear.
    for review in (oldest, middle, newest):
        assert review.title in content

    # Most-recent-first: newest appears before middle appears before oldest.
    pos_newest = content.index(newest.title)
    pos_middle = content.index(middle.title)
    pos_oldest = content.index(oldest.title)
    assert pos_newest < pos_middle < pos_oldest

    # Each review links to its detail permalink.
    for review in (oldest, middle, newest):
        assert reverse("catalog:review_detail", args=[review.slug]) in content


@pytest.mark.django_db
def test_home_shows_featured_brand_links(client):
    """Featured brands render with links to their permalinks (Req 6.5)."""
    brand = make_brand(name="Featured Brand Co", slug="featured-brand")
    # A qualifying review so the brand surfaces with stats.
    make_review(brand=brand, rating=4)

    response = client.get(reverse("catalog:home"))
    assert response.status_code == 200
    content = response.content.decode()

    assert "Featured Brand Co" in content
    assert reverse("catalog:brand_detail", args=["featured-brand"]) in content


# ---------------------------------------------------------------------------
# Brand detail (Req 7.1, 7.2, 7.4)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_brand_detail_returns_200_and_renders_required_fields(client):
    """Brand detail renders all required brand fields (Req 7.1, 7.2, 7.4)."""
    industry = make_industry(name="Home Services", slug="home-services")
    brand = make_brand(
        industry=industry,
        name="Reliable Repairs",
        slug="reliable-repairs",
        body="We fix things reliably and on time.",
        website_url="https://reliable.example.com",
        founded_year=1987,
        headquarters="Austin, TX",
    )
    # Two qualifying reviews -> average 4.5, plus verifies its reviews render.
    make_review(
        brand=brand, title="Fixed my sink", slug="fixed-my-sink", rating=4
    )
    make_review(
        brand=brand, title="Great plumber", slug="great-plumber", rating=5
    )

    response = client.get(reverse("catalog:brand_detail", args=["reliable-repairs"]))
    assert response.status_code == 200
    content = response.content.decode()

    # Name + industry.
    assert "Reliable Repairs" in content
    assert "Home Services" in content
    # Computed average rating (4 and 5 -> 4.5, rendered via floatformat:1).
    assert "4.5" in content
    # Website, founded year, headquarters.
    assert "https://reliable.example.com" in content
    assert "1987" in content
    assert "Austin, TX" in content
    # Brand body.
    assert "We fix things reliably and on time." in content
    # Its reviews are listed with links to their permalinks.
    assert "Fixed my sink" in content
    assert "Great plumber" in content
    assert reverse("catalog:review_detail", args=["fixed-my-sink"]) in content


@pytest.mark.django_db
def test_brand_detail_returns_404_for_missing_slug(client):
    """Requesting an unknown brand slug returns 404 (Req 7.1)."""
    response = client.get(reverse("catalog:brand_detail", args=["does-not-exist"]))
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Review detail (Req 8.1, 8.2, 8.4)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_review_detail_returns_200_and_renders_required_fields(client):
    """Review detail renders all required review fields (Req 8.1, 8.2, 8.4)."""
    brand = make_brand(name="Cloud Widgets", slug="cloud-widgets")
    review = make_review(
        brand=brand,
        title="Exceptional support",
        slug="exceptional-support",
        rating=5,
        reviewer_name="Sam Rivera",
        reviewer_location="Denver, CO",
        body="Their support team resolved my issue in minutes.",
    )

    response = client.get(reverse("catalog:review_detail", args=["exceptional-support"]))
    assert response.status_code == 200
    content = response.content.decode()

    # Title, rating, reviewer name, reviewer location, body.
    assert "Exceptional support" in content
    assert 'aria-label="Rating: 5 out of 5"' in content
    assert "Sam Rivera" in content
    assert "Denver, CO" in content
    assert "Their support team resolved my issue in minutes." in content
    # Link back to the parent brand's permalink (Req 8.4).
    assert "Cloud Widgets" in content
    assert reverse("catalog:brand_detail", args=["cloud-widgets"]) in content


@pytest.mark.django_db
def test_review_detail_returns_404_for_missing_slug(client):
    """Requesting an unknown review slug returns 404 (Req 8.1)."""
    response = client.get(reverse("catalog:review_detail", args=["no-such-review"]))
    assert response.status_code == 404
