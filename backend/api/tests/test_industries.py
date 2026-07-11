"""Contract tests for ``GET /api/industries/``.

Drives Django's test ``Client`` against the literal path so it's independent of
the API framework (DRF or Django Ninja).
"""

from http import HTTPStatus

import pytest
from django.test import Client

from catalog.models import Brand, Industry

INDUSTRIES_URL = "/api/industries/"


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_lists_all_industries_sorted_with_brand_counts(client):
    finance = Industry.objects.create(name="Finance", slug="finance", wp_term_id=1)
    Industry.objects.create(name="Aviation", slug="aviation", wp_term_id=2)
    Brand.objects.create(name="A", slug="a", industry=finance, wp_post_id=101)
    Brand.objects.create(name="B", slug="b", industry=finance, wp_post_id=102)

    response = client.get(INDUSTRIES_URL)

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Unpaginated plain list (no count/next/previous envelope).
    assert isinstance(data, list)
    # Sorted by name.
    assert [row["name"] for row in data] == ["Aviation", "Finance"]

    by_slug = {row["slug"]: row for row in data}
    assert set(by_slug) == {"aviation", "finance"}
    assert by_slug["finance"]["brand_count"] == 2
    assert by_slug["aviation"]["brand_count"] == 0
    # Exact card shape.
    assert set(data[0].keys()) == {"name", "slug", "brand_count"}


@pytest.mark.django_db
def test_empty_when_no_industries(client):
    response = client.get(INDUSTRIES_URL)
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []
