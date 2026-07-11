"""Property-based tests for the idempotent WordPress importer.

Uses Hypothesis to generate arbitrary source datasets and drives them through
``catalog.wp_import.importer.run_import`` to verify the importer's correctness
properties from the design document (Properties 3-7).

Rather than depend on a SQL dump, these tests build an in-memory
:class:`FakeSource` that satisfies the :class:`WordPressSource` protocol by
returning lists of the ``Source*`` dataclasses. This keeps the properties
source-agnostic and fast while exercising the real upsert orchestration.

Testing framework: Hypothesis + pytest-django (as specified in the design).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from catalog.models import Brand, ImportLedger, Industry, Review, Reviewer
from catalog.wp_import.importer import run_import
from catalog.wp_import.sources import (
    SourceBrand,
    SourceIndustry,
    SourceReview,
    SourceUser,
)


# --------------------------------------------------------------------------- #
# In-memory fake source
# --------------------------------------------------------------------------- #


class FakeSource:
    """An in-memory :class:`WordPressSource` backed by dataclass lists.

    The importer only calls the four generator methods, so returning stored
    lists is enough to stand in for ``SqlDumpSource``/``MariaDbSource`` with no
    DB dump or driver needed.
    """

    def __init__(self, industries, users, brands, reviews):
        self._industries = list(industries)
        self._users = list(users)
        self._brands = list(brands)
        self._reviews = list(reviews)

    def industries(self):
        return list(self._industries)

    def users(self):
        return list(self._users)

    def brands(self):
        return list(self._brands)

    def reviews(self):
        return list(self._reviews)


# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #

# Bounded, deterministic text so generated slugs/names stay valid and small.
_text = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=1,
    max_size=12,
)

_FIXED_DT = datetime(2026, 5, 19, 20, 28, 55, tzinfo=timezone.utc)


@st.composite
def dataset(draw):
    """Generate a coherent source dataset with valid FK references.

    Produces N industries, M users, P brands (each pointing at a real
    industry), and Q reviews (each pointing at a real brand; author either a
    real user or unresolved/None). Natural keys are unique within each model
    and slugs are unique across all brands and across all reviews.
    """
    n_industries = draw(st.integers(min_value=1, max_value=4))
    n_users = draw(st.integers(min_value=1, max_value=4))
    n_brands = draw(st.integers(min_value=1, max_value=5))
    n_reviews = draw(st.integers(min_value=0, max_value=12))

    industries = [
        SourceIndustry(wp_term_id=100 + i, name=f"Industry {i}", slug=f"industry-{i}")
        for i in range(n_industries)
    ]
    users = [
        SourceUser(
            wp_user_id=200 + u,
            user_login=f"user{u}",
            display_name=f"User {u}",
            email=f"user{u}@example.com",
        )
        for u in range(n_users)
    ]

    brands = []
    for b in range(n_brands):
        industry_ref = draw(st.sampled_from(industries)).wp_term_id
        brands.append(
            SourceBrand(
                wp_post_id=300 + b,
                name=f"Brand {b}",
                slug=f"brand-{b}",
                body=draw(_text),
                wp_post_date=_FIXED_DT,
                industry_wp_term_id=industry_ref,
                website_url=f"https://brand{b}.example",
                founded_year=draw(st.integers(min_value=1900, max_value=2025)),
                headquarters=draw(_text),
            )
        )

    reviews = []
    for r in range(n_reviews):
        brand_ref = draw(st.sampled_from(brands)).wp_post_id
        # Author: a real user, or None (unresolved) some of the time.
        author = draw(
            st.one_of(
                st.none(),
                st.sampled_from([u.wp_user_id for u in users]),
            )
        )
        reviews.append(
            SourceReview(
                wp_post_id=400 + r,
                title=f"Review {r}",
                slug=f"review-{r}",
                body=draw(_text),
                wp_post_date=_FIXED_DT,
                rating=draw(st.integers(min_value=0, max_value=5)),
                reviewer_name=draw(_text),
                reviewer_location=draw(_text),
                brand_wp_post_id=brand_ref,
                wp_user_id=author,
            )
        )

    return industries, users, brands, reviews


def _snapshot_counts():
    return {
        "industries": Industry.objects.count(),
        "reviewers": Reviewer.objects.count(),
        "brands": Brand.objects.count(),
        "reviews": Review.objects.count(),
    }


def _snapshot_fields():
    """A stable, comparable snapshot of every stored row's mapped fields."""
    return {
        "industries": sorted(
            Industry.objects.values_list("wp_term_id", "name", "slug")
        ),
        "reviewers": sorted(
            Reviewer.objects.values_list(
                "wp_user_id", "display_name", "wp_user_login", "email"
            )
        ),
        "brands": sorted(
            Brand.objects.values_list(
                "wp_post_id",
                "name",
                "slug",
                "body",
                "website_url",
                "founded_year",
                "headquarters",
                "industry__wp_term_id",
                "wp_post_date",
            )
        ),
        "reviews": sorted(
            Review.objects.values_list(
                "wp_post_id",
                "title",
                "slug",
                "body",
                "rating",
                "reviewer_name",
                "reviewer_location",
                "brand__wp_post_id",
                "reviewer__wp_user_id",
                "wp_post_date",
            )
        ),
    }


def _reset_db():
    """Empty every imported table + the ledger between Hypothesis examples."""
    Review.objects.all().delete()
    Brand.objects.all().delete()
    Reviewer.objects.all().delete()
    Industry.objects.all().delete()
    ImportLedger.objects.all().delete()


# --------------------------------------------------------------------------- #
# Property 3: Import idempotency
# --------------------------------------------------------------------------- #


@pytest.mark.django_db(transaction=True)
@given(data=dataset())
@settings(max_examples=50, deadline=None)
def test_property_import_idempotency(data):
    """**Validates: Requirements 5.3, 5.4**

    Running the import twice against an unchanged source leaves per-model
    counts identical to after the first run, and every stored field equal to
    the first run (zero updates on the second pass).
    """
    industries, users, brands, reviews = data
    source = FakeSource(industries, users, brands, reviews)
    try:
        run_import(source)
        counts_after_first = _snapshot_counts()
        fields_after_first = _snapshot_fields()

        summary = run_import(source)
        counts_after_second = _snapshot_counts()
        fields_after_second = _snapshot_fields()

        assert counts_after_second == counts_after_first, (
            f"Counts changed on re-run: {counts_after_first} -> {counts_after_second}"
        )
        assert fields_after_second == fields_after_first, (
            "Stored fields changed on an unchanged re-run"
        )
        # Nothing should have been created or updated on the second run.
        assert summary.industries_created == 0
        assert summary.reviewers_created == 0
        assert summary.brands_created == 0
        assert summary.reviews_created == 0
        assert summary.industries_updated == 0
        assert summary.reviewers_updated == 0
        assert summary.brands_updated == 0
        assert summary.reviews_updated == 0
    finally:
        _reset_db()


# --------------------------------------------------------------------------- #
# Property 4: Update propagation
# --------------------------------------------------------------------------- #


@pytest.mark.django_db(transaction=True)
@given(data=dataset())
@settings(max_examples=50, deadline=None)
def test_property_update_propagation(data):
    """**Validates: Requirements 5.5, 5.6**

    When a source record's mapped field changes between runs, the second run
    updates that row in place; unrelated rows are unchanged.
    """
    industries, users, brands, reviews = data
    source = FakeSource(industries, users, brands, reviews)
    try:
        run_import(source)

        # Mutate the first brand's name; capture unrelated brands' state.
        target = brands[0]
        new_name = target.name + " CHANGED"
        target.name = new_name

        unrelated_before = {
            b.wp_post_id: Brand.objects.get(wp_post_id=b.wp_post_id).name
            for b in brands[1:]
        }

        run_import(FakeSource(industries, users, brands, reviews))

        updated = Brand.objects.get(wp_post_id=target.wp_post_id)
        assert updated.name == new_name, "Changed source field did not propagate"

        for wp_id, name_before in unrelated_before.items():
            assert Brand.objects.get(wp_post_id=wp_id).name == name_before, (
                f"Unrelated brand {wp_id} changed unexpectedly"
            )
    finally:
        _reset_db()


# --------------------------------------------------------------------------- #
# Property 5: Deletion preservation
# --------------------------------------------------------------------------- #


@pytest.mark.django_db(transaction=True)
@given(data=dataset())
@settings(max_examples=50, deadline=None)
def test_property_deletion_preservation(data):
    """**Validates: Requirements 5.7**

    Rows deleted from the DB between runs are not recreated by a subsequent
    import (the ledger blocks resurrection), and other rows are unaffected.
    """
    industries, users, brands, reviews = data
    source = FakeSource(industries, users, brands, reviews)
    try:
        run_import(source)

        # Delete the first brand (cascades to its reviews) between runs.
        target_wp_id = brands[0].wp_post_id
        deleted_review_ids = list(
            Review.objects.filter(brand__wp_post_id=target_wp_id).values_list(
                "wp_post_id", flat=True
            )
        )
        Brand.objects.filter(wp_post_id=target_wp_id).delete()

        surviving_brand_ids_before = set(
            Brand.objects.values_list("wp_post_id", flat=True)
        )

        run_import(FakeSource(industries, users, brands, reviews))

        # The deleted brand must stay deleted.
        assert not Brand.objects.filter(wp_post_id=target_wp_id).exists(), (
            "Deleted brand was resurrected on re-run"
        )
        # Its reviews must stay gone too.
        for rid in deleted_review_ids:
            assert not Review.objects.filter(wp_post_id=rid).exists(), (
                f"Review {rid} of a deleted brand was resurrected"
            )
        # Every other brand that survived must still be present.
        surviving_brand_ids_after = set(
            Brand.objects.values_list("wp_post_id", flat=True)
        )
        assert surviving_brand_ids_before <= surviving_brand_ids_after, (
            "An unrelated brand was lost across the re-run"
        )
    finally:
        _reset_db()


# --------------------------------------------------------------------------- #
# Property 6: Reviewer de-duplication
# --------------------------------------------------------------------------- #


@pytest.mark.django_db(transaction=True)
@given(data=dataset())
@settings(max_examples=50, deadline=None)
def test_property_reviewer_deduplication(data):
    """**Validates: Requirements 4.1, 4.2, 4.3**

    For any set of reviews sharing a ``post_author``, exactly one Reviewer
    exists for that ``wp_user_id`` and every such review links to it.
    """
    industries, users, brands, reviews = data
    source = FakeSource(industries, users, brands, reviews)
    try:
        run_import(source)

        # Every wp_user_id referenced as a review author...
        referenced = {r.wp_user_id for r in reviews if r.wp_user_id is not None}
        for wp_user_id in referenced:
            # ...yields exactly one Reviewer.
            matches = Reviewer.objects.filter(wp_user_id=wp_user_id)
            assert matches.count() == 1, (
                f"Expected exactly one Reviewer for wp_user_id={wp_user_id}, "
                f"found {matches.count()}"
            )
            reviewer = matches.get()
            # ...and all reviews with that author link to that one Reviewer.
            expected_slugs = {
                r.slug for r in reviews if r.wp_user_id == wp_user_id
            }
            linked_slugs = set(
                Review.objects.filter(reviewer=reviewer).values_list(
                    "slug", flat=True
                )
            )
            assert expected_slugs <= linked_slugs, (
                f"Not all reviews for wp_user_id={wp_user_id} link to the "
                f"single Reviewer"
            )
    finally:
        _reset_db()


# --------------------------------------------------------------------------- #
# Property 7: Slug uniqueness preserved
# --------------------------------------------------------------------------- #


@pytest.mark.django_db(transaction=True)
@given(data=dataset())
@settings(max_examples=50, deadline=None)
def test_property_slug_uniqueness(data):
    """**Validates: Requirements 1.9, 9.1, 9.2**

    After importing any valid source, all Brand slugs are unique and all
    Review slugs are unique.
    """
    industries, users, brands, reviews = data
    source = FakeSource(industries, users, brands, reviews)
    try:
        run_import(source)

        brand_slugs = list(Brand.objects.values_list("slug", flat=True))
        review_slugs = list(Review.objects.values_list("slug", flat=True))

        assert len(brand_slugs) == len(set(brand_slugs)), (
            "Duplicate Brand slug(s) after import"
        )
        assert len(review_slugs) == len(set(review_slugs)), (
            "Duplicate Review slug(s) after import"
        )
    finally:
        _reset_db()
