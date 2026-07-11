"""Domain models for the catalog app.

Clean relational schema for the WordPress -> Django migration. Each imported
model carries the stable WordPress natural key (``wp_post_id`` / ``wp_user_id``
/ ``wp_term_id``) with a unique constraint so the idempotent import can match
existing rows on re-run and resolve foreign keys.

See the design "Data Models" section for the field-mapping table and the
"Constraints and indexing" rules that this module implements.
"""

from django.db import models
from django.db.models import Avg

from catalog.querysets import BrandQuerySet


class Industry(models.Model):
    """A business category, migrated from the WordPress ``industry`` taxonomy."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    # WordPress natural key (wp_terms.term_id) — idempotency match key.
    wp_term_id = models.BigIntegerField(unique=True)

    class Meta:
        verbose_name_plural = "industries"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Reviewer(models.Model):
    """The author of a Review, migrated from WordPress ``wp_users``."""

    display_name = models.CharField(max_length=255)
    wp_user_login = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)

    # WordPress natural key (wp_users.ID) — idempotency match key.
    wp_user_id = models.BigIntegerField(unique=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name


class Brand(models.Model):
    """A reviewed company, migrated from the WordPress ``brand`` post type."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    body = models.TextField(blank=True)

    # First-class ACF profile fields (Req 3.1).
    website_url = models.URLField(max_length=500, blank=True)
    founded_year = models.PositiveIntegerField(null=True, blank=True)
    headquarters = models.CharField(max_length=255, blank=True)

    # WordPress-authored ACF average, retained for audit/comparison (Req 2.1).
    migrated_average_rating = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True
    )

    # Retained Yoast SEO metadata (Req 3.4).
    seo_title = models.CharField(max_length=255, blank=True)
    seo_metadesc = models.TextField(blank=True)

    # Industry FK: non-null, protect against deleting an in-use industry.
    industry = models.ForeignKey(
        Industry,
        on_delete=models.PROTECT,
        related_name="brands",
    )

    # WordPress natural key (wp_posts.ID) and original publish date.
    wp_post_id = models.BigIntegerField(unique=True)
    wp_post_date = models.DateTimeField(null=True, blank=True)

    objects = BrandQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def computed_average_rating(self):
        """Authoritative average rating for single-object use (Req 2.2, 2.6).

        Mirrors ``BrandQuerySet.with_stats()``: the mean of this brand's
        qualifying review ratings (rating >= 1) on a 0-5 scale, or ``None``
        when there are no qualifying reviews (Req 2.3, 2.4, 2.5).

        When the instance was loaded via ``with_stats()`` the annotated value
        is reused (stored through the setter below) so a detail page never
        triggers an N+1 query; otherwise the same aggregate is computed
        directly, guaranteeing the property and annotation agree.
        """
        if "computed_average_rating" in self.__dict__:
            return self.__dict__["computed_average_rating"]
        return self.reviews.filter(rating__gte=1).aggregate(avg=Avg("rating"))["avg"]

    @computed_average_rating.setter
    def computed_average_rating(self, value):
        # Lets ``with_stats()`` assign the annotated value onto the instance
        # despite the property defined above.
        self.__dict__["computed_average_rating"] = value


class Review(models.Model):
    """A customer review, migrated from the WordPress ``review`` post type."""

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    body = models.TextField(blank=True)

    # First-class ACF review field (Req 3.2). Stored as received; values < 1
    # are treated as missing during aggregation but preserved here.
    rating = models.PositiveSmallIntegerField(null=True, blank=True)

    # Per-review display attributes (Req 1.8, 4.4). Kept on the review so they
    # survive an unresolved author and can differ from the canonical reviewer.
    reviewer_name = models.CharField(max_length=255, blank=True)
    reviewer_location = models.CharField(max_length=255, blank=True)

    # Brand FK: non-null, cascade so reviews die with their brand.
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    # Reviewer FK: nullable, set null when a reviewer identity is removed or the
    # author cannot be resolved (Req 1.7, 4.4).
    reviewer = models.ForeignKey(
        Reviewer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
    )

    # WordPress natural key (wp_posts.ID) and original publish date.
    wp_post_id = models.BigIntegerField(unique=True)
    wp_post_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-wp_post_date"]
        indexes = [
            # `rating` is filtered on every stats query (Q(rating__gte=1) in
            # with_stats() and the top-review prefetch), so index it to avoid a
            # full scan of the most-hit path as the review table grows.
            models.Index(fields=["rating"], name="review_rating_idx"),
            # Serves the "top review per brand" access pattern (filter rating>=1,
            # partition by brand, order by rating desc then date desc) and the
            # per-brand aggregation grouping.
            models.Index(
                fields=["brand", "-rating", "-wp_post_date"],
                name="review_brand_top_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title


class ImportLedger(models.Model):
    """Records every natural key the import has ever created, per model.

    Used by the idempotent importer to distinguish "never imported" from
    "imported then manually deleted" so deletions are preserved on re-run
    (Req 5.7).
    """

    model_label = models.CharField(max_length=32)  # "brand" | "review" | ...
    wp_id = models.BigIntegerField()

    class Meta:
        unique_together = ("model_label", "wp_id")

    def __str__(self) -> str:
        return f"{self.model_label}:{self.wp_id}"
