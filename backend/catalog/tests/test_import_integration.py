"""Integration test for the WordPress importer against the real ``db/dump.sql``.

Unlike the property tests (which drive an in-memory fake source), this test
runs the real :class:`SqlDumpSource` over the committed dump at
``settings.REPO_ROOT/db/dump.sql`` and asserts the end-to-end behaviours from
the design's "Import integration" testing strategy:

* seeded counts (5 industries, 5 brands, 8 reviewers, 60 reviews),
* a re-run leaves counts unchanged and reports zero updates (idempotency —
  this only holds once ``wp_post_date`` is parsed as a timezone-aware datetime),
* a brand deleted between runs stays deleted (and its reviews stay gone),
* a mutated source field propagates on the next run.

Validates: Requirements 5.3, 5.4, 5.6, 5.7.
"""

from __future__ import annotations

import pytest
from django.conf import settings

from catalog.models import Brand, Industry, Review, Reviewer
from catalog.wp_import.importer import run_import
from catalog.wp_import.sources import SqlDumpSource

DUMP_PATH = settings.REPO_ROOT / "db" / "dump.sql"

# Expected seeded volume from the WordPress dump.
EXPECTED_INDUSTRIES = 5
EXPECTED_BRANDS = 5
EXPECTED_REVIEWERS = 8
EXPECTED_REVIEWS = 60


pytestmark = pytest.mark.skipif(
    not DUMP_PATH.exists(), reason=f"dump not found at {DUMP_PATH}"
)


def _counts():
    return {
        "industries": Industry.objects.count(),
        "brands": Brand.objects.count(),
        "reviewers": Reviewer.objects.count(),
        "reviews": Review.objects.count(),
    }


def _total_updated(summary) -> int:
    return (
        summary.industries_updated
        + summary.reviewers_updated
        + summary.brands_updated
        + summary.reviews_updated
    )


@pytest.mark.django_db
def test_import_seeds_expected_counts():
    """First import against an empty DB creates the seeded volume (Req 5.3)."""
    run_import(SqlDumpSource(str(DUMP_PATH)))

    assert _counts() == {
        "industries": EXPECTED_INDUSTRIES,
        "brands": EXPECTED_BRANDS,
        "reviewers": EXPECTED_REVIEWERS,
        "reviews": EXPECTED_REVIEWS,
    }


@pytest.mark.django_db
def test_reimport_is_idempotent_and_reports_zero_updates():
    """A second run leaves counts unchanged and reports zero updates.

    The zero-updates assertion is the payoff of the timezone-aware
    ``wp_post_date`` fix: without it, every row would compare unequal on
    ``wp_post_date`` (naive vs aware) and be marked "updated" forever.

    Validates: Requirements 5.4.
    """
    run_import(SqlDumpSource(str(DUMP_PATH)))
    counts_after_first = _counts()

    summary = run_import(SqlDumpSource(str(DUMP_PATH)))
    counts_after_second = _counts()

    assert counts_after_second == counts_after_first
    assert _total_updated(summary) == 0, (
        "Re-running against an unchanged dump reported updates; "
        "expected a fully idempotent no-op"
    )


@pytest.mark.django_db
def test_deleted_brand_stays_deleted_on_reimport():
    """A manually deleted brand (and its reviews) is not resurrected (Req 5.7)."""
    run_import(SqlDumpSource(str(DUMP_PATH)))

    victim = Brand.objects.first()
    victim_wp_id = victim.wp_post_id
    deleted_review_ids = list(
        Review.objects.filter(brand=victim).values_list("wp_post_id", flat=True)
    )
    assert deleted_review_ids, "expected the seeded brand to have reviews"

    victim.delete()  # cascades to its reviews

    run_import(SqlDumpSource(str(DUMP_PATH)))

    assert not Brand.objects.filter(wp_post_id=victim_wp_id).exists(), (
        "Deleted brand was resurrected on re-import"
    )
    for rid in deleted_review_ids:
        assert not Review.objects.filter(wp_post_id=rid).exists(), (
            f"Review {rid} of the deleted brand was resurrected"
        )
    # The rest of the catalog is intact.
    assert Brand.objects.count() == EXPECTED_BRANDS - 1
    assert Review.objects.count() == EXPECTED_REVIEWS - len(deleted_review_ids)


class _MutatedNameSource:
    """Wraps a real source but renames one brand to exercise update propagation."""

    def __init__(self, inner: SqlDumpSource, target_wp_post_id: int, new_name: str):
        self._inner = inner
        self._target = target_wp_post_id
        self._new_name = new_name

    def industries(self):
        return self._inner.industries()

    def users(self):
        return self._inner.users()

    def brands(self):
        for brand in self._inner.brands():
            if brand.wp_post_id == self._target:
                brand.name = self._new_name
            yield brand

    def reviews(self):
        return self._inner.reviews()


@pytest.mark.django_db
def test_mutated_source_field_propagates_on_reimport():
    """A changed source field updates the stored row in place (Req 5.6)."""
    run_import(SqlDumpSource(str(DUMP_PATH)))

    target = Brand.objects.first()
    new_name = target.name + " (Renamed)"

    mutated = _MutatedNameSource(
        SqlDumpSource(str(DUMP_PATH)), target.wp_post_id, new_name
    )
    summary = run_import(mutated)

    refreshed = Brand.objects.get(wp_post_id=target.wp_post_id)
    assert refreshed.name == new_name, "Mutated brand name did not propagate"
    assert summary.brands_updated >= 1
    # Count is unchanged — this was an update, not an insert.
    assert Brand.objects.count() == EXPECTED_BRANDS
