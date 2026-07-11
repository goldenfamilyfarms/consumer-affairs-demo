"""Property-based tests for the computed average rating definition.

**Validates: Requirements 2.3, 2.4, 2.5**

Property 1: Average rating range/definition
For any set of reviews on a brand, `computed_average_rating` equals the
arithmetic mean of ratings >= 1, lies in [1, 5], and is null iff no review
has rating >= 1. Ratings < 1 never affect the result.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from catalog.models import Brand, Industry, Review


# Strategy: a list of ratings in range [0, 5] representing the reviews for a brand.
# We include 0 as a "below threshold" rating that should be excluded from the
# average per Req 2.4. The list can be empty (no reviews at all).
ratings_strategy = st.lists(st.integers(min_value=0, max_value=5), min_size=0, max_size=30)


@pytest.mark.django_db(transaction=True)
class TestAverageRatingDefinition:
    """Property 1: Average rating range/definition."""

    @given(ratings=ratings_strategy)
    @settings(max_examples=200, deadline=None)
    def test_computed_average_rating_property(self, ratings):
        """
        **Validates: Requirements 2.3, 2.4, 2.5**

        For any set of reviews on a brand:
        - computed_average_rating equals the arithmetic mean of ratings >= 1
        - The result lies in [1, 5] when not null
        - The result is null iff no review has rating >= 1
        - Ratings < 1 never affect the result
        """
        # --- Setup: create a brand with the given set of review ratings ---
        industry, _ = Industry.objects.get_or_create(
            wp_term_id=1,
            defaults={"name": "Test Industry", "slug": "test-industry"},
        )

        # Use a unique wp_post_id to avoid conflicts across hypothesis examples
        brand = Brand.objects.create(
            name="Test Brand",
            slug="test-brand-prop1",
            industry=industry,
            wp_post_id=99999,
        )

        try:
            # Create reviews with the generated ratings
            for i, rating_val in enumerate(ratings):
                Review.objects.create(
                    title=f"Review {i}",
                    slug=f"review-prop1-{i}",
                    brand=brand,
                    rating=rating_val,
                    wp_post_id=100000 + i,
                )

            # --- Compute the expected value ---
            qualifying_ratings = [r for r in ratings if r >= 1]

            if not qualifying_ratings:
                expected_avg = None
            else:
                expected_avg = sum(qualifying_ratings) / len(qualifying_ratings)

            # --- Test via the queryset annotation (with_stats) ---
            annotated_brand = Brand.objects.with_stats().get(pk=brand.pk)
            actual_annotation = annotated_brand.computed_average_rating

            # --- Test via the model property (single-object path) ---
            fresh_brand = Brand.objects.get(pk=brand.pk)
            actual_property = fresh_brand.computed_average_rating

            # --- Assertions ---

            # 1. Null iff no qualifying reviews (Req 2.5)
            if expected_avg is None:
                assert actual_annotation is None, (
                    f"Expected null annotation but got {actual_annotation} "
                    f"for ratings={ratings}"
                )
                assert actual_property is None, (
                    f"Expected null property but got {actual_property} "
                    f"for ratings={ratings}"
                )
            else:
                assert actual_annotation is not None, (
                    f"Expected non-null annotation but got None "
                    f"for ratings={ratings}"
                )
                assert actual_property is not None, (
                    f"Expected non-null property but got None "
                    f"for ratings={ratings}"
                )

                # 2. Equals the arithmetic mean of ratings >= 1 (Req 2.3)
                assert abs(float(actual_annotation) - expected_avg) < 1e-9, (
                    f"Annotation {actual_annotation} != expected {expected_avg} "
                    f"for ratings={ratings}"
                )
                assert abs(float(actual_property) - expected_avg) < 1e-9, (
                    f"Property {actual_property} != expected {expected_avg} "
                    f"for ratings={ratings}"
                )

                # 3. Result lies in [1, 5] (since qualifying ratings are in [1,5])
                assert 1.0 <= float(actual_annotation) <= 5.0, (
                    f"Annotation {actual_annotation} outside [1, 5] "
                    f"for ratings={ratings}"
                )
                assert 1.0 <= float(actual_property) <= 5.0, (
                    f"Property {actual_property} outside [1, 5] "
                    f"for ratings={ratings}"
                )

            # 4. Ratings < 1 never affect the result (Req 2.4)
            # Verified implicitly: we only include ratings >= 1 in expected_avg,
            # so if the actual matches expected, sub-1 ratings were excluded.
            # Additionally, explicitly verify by adding a zero-rating review
            # and checking the result doesn't change.
            Review.objects.create(
                title="Extra zero-rating review",
                slug="review-prop1-extra-zero",
                brand=brand,
                rating=0,
                wp_post_id=200000,
            )

            annotated_after = Brand.objects.with_stats().get(pk=brand.pk)
            actual_after = annotated_after.computed_average_rating

            if expected_avg is None:
                assert actual_after is None, (
                    "Adding a zero-rating review changed null result to "
                    f"{actual_after}"
                )
            else:
                assert abs(float(actual_after) - expected_avg) < 1e-9, (
                    f"Adding a zero-rating review changed result from "
                    f"{expected_avg} to {actual_after}"
                )

        finally:
            # Clean up to avoid unique constraint violations across examples
            Review.objects.filter(brand=brand).delete()
            brand.delete()
