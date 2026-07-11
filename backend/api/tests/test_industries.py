"""Contract tests for ``GET /api/industries/``.

The endpoint backs the React filter dropdown so it can load the full set of
industries independently of the brand result set (fixing the cold-start where
the dropdown would otherwise be empty or incomplete).
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from catalog.models import Brand, Industry


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_lists_all_industries_sorted_with_brand_counts(client):
    finance = Industry.objects.create(name="Finance", slug="finance", wp_term_id=1)
    Industry.objects.create(name="Aviation", slug="aviation", wp_term_id=2)
    Brand.objects.create(name="A", slug="a", industry=finance, wp_post_id=101)
    Brand.objects.create(name="B", slug="b", industry=finance, wp_post_id=102)

    response = client.get(reverse("api:industry-list"))

    assert response.status_code == status.HTTP_200_OK
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
    response = client.get(reverse("api:industry-list"))
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []
