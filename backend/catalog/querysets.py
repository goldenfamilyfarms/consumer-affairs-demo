"""Custom querysets for the catalog app.

Keeps the computed-rating aggregation in the database so it scales and stays
consistent with the single-object rule on the model (see the design
"Computed average rating" section).
"""

from django.db.models import Avg, Count, Q, QuerySet

# A review only counts toward a brand's statistics when its rating is a real
# score of 1 or greater. Ratings below 1 are treated as missing data and are
# excluded from both the average and the qualifying-review count (Req 2.4).
QUALIFYING_REVIEW = Q(reviews__rating__gte=1)


class BrandQuerySet(QuerySet):
    """Queryset for :class:`~catalog.models.Brand` with rating aggregation."""

    def with_stats(self):
        """Annotate each brand with its review stats.

        - ``review_count``: number of qualifying reviews (rating >= 1).
        - ``computed_average_rating``: mean of qualifying review ratings on a
          0-5 scale, or ``NULL`` when the brand has no qualifying reviews
          (Req 2.3, 2.5). ``Avg`` naturally yields ``NULL`` over an empty set.

        Aggregation stays in the database so the values are sortable and cheap
        at scale (Req 2.2, 2.6).
        """
        return self.annotate(
            review_count=Count("reviews", filter=QUALIFYING_REVIEW),
            computed_average_rating=Avg("reviews__rating", filter=QUALIFYING_REVIEW),
        )
