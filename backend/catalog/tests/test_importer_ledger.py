"""Explicit example tests for the ImportLedger skip-on-deletion branch.

Property 5 (deletion preservation) covers this over generated inputs, but this
is the single most important correctness claim in the importer, so it also gets
a concrete, readable example that pins the exact branch: a row imported on run 1,
deleted between runs, must NOT be recreated on run 2 — and must be counted as a
skip (neither created nor updated), with its ledger entry intact.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from catalog.models import Brand, ImportLedger, Review
from catalog.wp_import.importer import run_import
from catalog.wp_import.sources import (
    SourceBrand,
    SourceIndustry,
    SourceReview,
    SourceUser,
)

_DT = datetime(2024, 1, 1, tzinfo=timezone.utc)


class ListSource:
    """Minimal in-memory WordPressSource backed by dataclass lists."""

    def __init__(self, industries, users, brands, reviews):
        self._industries = industries
        self._users = users
        self._brands = brands
        self._reviews = reviews

    def industries(self):
        return list(self._industries)

    def users(self):
        return list(self._users)

    def brands(self):
        return list(self._brands)

    def reviews(self):
        return list(self._reviews)


def _fresh_source():
    """A one-of-everything source (a new instance per run, like a real source)."""
    return ListSource(
        [SourceIndustry(wp_term_id=1, name="Finance", slug="finance")],
        [SourceUser(wp_user_id=2, user_login="jane", display_name="Jane Doe")],
        [
            SourceBrand(
                wp_post_id=10,
                name="Acme",
                slug="acme",
                industry_wp_term_id=1,
                wp_post_date=_DT,
            )
        ],
        [
            SourceReview(
                wp_post_id=100,
                title="Great",
                slug="great",
                rating=5,
                brand_wp_post_id=10,
                wp_user_id=2,
                wp_post_date=_DT,
            )
        ],
    )


@pytest.mark.django_db
def test_deleted_review_is_not_resurrected_and_counts_as_skip():
    run_import(_fresh_source())
    assert Review.objects.filter(wp_post_id=100).exists()
    assert ImportLedger.objects.filter(model_label="review", wp_id=100).exists()

    # An admin deletes the review from Django between runs. The ledger entry
    # lives in a separate table, so it survives the row deletion.
    Review.objects.filter(wp_post_id=100).delete()
    assert ImportLedger.objects.filter(model_label="review", wp_id=100).exists()

    summary = run_import(_fresh_source())

    # The exact skip branch: the ledger has the key but the row is gone, so the
    # importer neither recreates nor updates it.
    assert not Review.objects.filter(wp_post_id=100).exists()
    assert summary.reviews_created == 0
    assert summary.reviews_updated == 0
    assert ImportLedger.objects.filter(model_label="review", wp_id=100).exists()


@pytest.mark.django_db
def test_deleted_brand_is_not_resurrected():
    run_import(_fresh_source())
    assert Brand.objects.filter(wp_post_id=10).exists()

    # Deleting the brand cascades to its review.
    Brand.objects.filter(wp_post_id=10).delete()
    assert not Review.objects.filter(wp_post_id=100).exists()

    summary = run_import(_fresh_source())

    # Brand stays deleted (ledger blocks re-creation) and isn't counted created.
    assert not Brand.objects.filter(wp_post_id=10).exists()
    assert summary.brands_created == 0
    # Its review can't be recreated either (brand FK can't resolve).
    assert not Review.objects.filter(wp_post_id=100).exists()
