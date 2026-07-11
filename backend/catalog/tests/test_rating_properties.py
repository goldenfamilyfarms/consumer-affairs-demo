"""Property-based tests for the computed average rating logic.

Uses Hypothesis to generate brands with arbitrary review sets and verifies
that the correctness properties from the design document hold universally.

Testing framework: Hypothesis + pytest-django (as specified in the design).
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from catalog.models import Brand, Industry, Review, Reviewer


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Ratings in the range 0..5. Ratings < 1 are treated as missing data by the
# computed average logic (Req 2.4). We include 0 to exercise that exclusion.
rating_strategy = st.integers(min_value=0, max_value=5)

# A list of ratings representing the reviews a brand will have.
# Allow empty lists (brand with no reviews) and lists up to 30 reviews.
review_ratings_strategy = st.lists(rating_strategy, min_size=0, max_size=30)


# ---------------------------------------------------------------------------
# Property 1: Average rating range/definition
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@given(ratings=review_ratings_strategy)
@settings(max_examples=100, deadline=None)
def test_property_average_rating_definition(ratings):
    """**Validates: Requirements 2.3, 2.4, 2.5**

    For any set of reviews on a brand, ``computed_average_rating``:

    - equals the arithmetic mean of the ratings ``>= 1`` (Req 2.3),
    - lies within the ``[1, 5]`` scale when defined,
    - is ``null`` iff no review has ``rating >= 1`` (Req 2.5), and
    - is unaffected by ratings ``< 1`` (Req 2.4 — they are missing data).
    """
    # Qualifying ratings are the source of truth for the expected mean.
    qualifying = [r for r in ratings if r >= 1]
    expected = (sum(qualifying) / len(qualifying)) if qualifying else None

    # --- Setup: create a brand with reviews carrying the generated ratings ---
    industry, _ = Industry.objects.get_or_create(
        wp_term_id=1,
        defaults={"name": "Test Industry", "slug": "test-industry"},
    )

    brand = Brand.objects.create(
        name="Test Brand",
        slug="test-brand-prop1",
        industry=industry,
        wp_post_id=88888,
    )

    try:
        for i, rating in enumerate(ratings):
            Review.objects.create(
                title=f"Review {i}",
                slug=f"test-review-prop1-{i}",
                rating=rating,
                brand=brand,
                wp_post_id=80000 + i,
            )

        # Compute via the database annotation (the authoritative definition).
        annotated_brand = Brand.objects.with_stats().get(pk=brand.pk)
        computed = annotated_brand.computed_average_rating

        if expected is None:
            # Req 2.5: null iff no qualifying review exists.
            assert computed is None, (
                f"Expected null average with no qualifying reviews, got {computed}"
            )
        else:
            assert computed is not None, (
                f"Expected {expected} but computed average was null"
            )
            # Req 2.3 + Req 2.4: equals the mean of ratings >= 1 only.
            assert math.isclose(float(computed), expected, rel_tol=1e-9), (
                f"Computed ({computed}) != mean of qualifying ratings ({expected})"
            )
            # The mean of values in [1, 5] must itself lie in [1, 5].
            assert 1 <= float(computed) <= 5, (
                f"Computed average {computed} outside the [1, 5] scale"
            )
    finally:
        # Clean up so each Hypothesis example starts fresh.
        Review.objects.filter(brand=brand).delete()
        brand.delete()


# ---------------------------------------------------------------------------
# Property 2: Property vs. annotation agreement
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@given(ratings=review_ratings_strategy)
@settings(max_examples=100, deadline=None)
def test_property_annotation_agreement(ratings):
    """**Validates: Requirements 2.2, 2.6**

    For any brand, the Brand.computed_average_rating property and the
    with_stats() annotation produce the same value (both null or both
    equal within floating-point tolerance).
    """
    # --- Setup: create a brand with reviews carrying the generated ratings ---
    industry, _ = Industry.objects.get_or_create(
        wp_term_id=1,
        defaults={"name": "Test Industry", "slug": "test-industry"},
    )

    # Use a unique wp_post_id per test run to avoid conflicts; clean up after.
    brand = Brand.objects.create(
        name="Test Brand",
        slug="test-brand-prop2",
        industry=industry,
        wp_post_id=99999,
    )

    try:
        for i, rating in enumerate(ratings):
            Review.objects.create(
                title=f"Review {i}",
                slug=f"test-review-prop2-{i}",
                rating=rating,
                brand=brand,
                wp_post_id=90000 + i,
            )

        # --- Compute via model property (fresh instance, no annotation) ---
        fresh_brand = Brand.objects.get(pk=brand.pk)
        property_value = fresh_brand.computed_average_rating

        # --- Compute via queryset annotation ---
        annotated_brand = Brand.objects.with_stats().get(pk=brand.pk)
        annotation_value = annotated_brand.computed_average_rating

        # --- Assert agreement ---
        if property_value is None:
            assert annotation_value is None, (
                f"Property returned None but annotation returned {annotation_value}"
            )
        else:
            assert annotation_value is not None, (
                f"Property returned {property_value} but annotation returned None"
            )
            # Allow floating-point tolerance (database may use different precision)
            assert math.isclose(float(property_value), float(annotation_value), rel_tol=1e-9), (
                f"Property ({property_value}) != Annotation ({annotation_value})"
            )
    finally:
        # Clean up so each Hypothesis example starts fresh.
        Review.objects.filter(brand=brand).delete()
        brand.delete()
