"""Django Ninja (Pydantic) schemas for the brand listing API.

These replace DRF serializers. Field resolvers pull the computed/related values
off the annotated Brand instances, so the endpoint returns the same card
contract as the DRF baseline:

    { name, slug, industry, industry_slug, average_rating, review_count,
      short_description, top_review_snippet }
"""

from __future__ import annotations

from typing import List, Optional

from ninja import Schema

from api.queries import excerpt, top_review_for
from catalog.models import Brand


class BrandCardSchema(Schema):
    """One brand card. Resolvers read annotations/relations off the instance."""

    name: str
    slug: str
    industry: str
    industry_slug: str
    average_rating: Optional[float]
    review_count: int
    short_description: Optional[str]
    top_review_snippet: Optional[str]

    @staticmethod
    def resolve_industry(obj: Brand) -> str:
        return obj.industry.name

    @staticmethod
    def resolve_industry_slug(obj: Brand) -> str:
        return obj.industry.slug

    @staticmethod
    def resolve_average_rating(obj: Brand):
        avg = obj.computed_average_rating
        return round(float(avg), 2) if avg is not None else None

    @staticmethod
    def resolve_short_description(obj: Brand):
        return excerpt(obj.body)

    @staticmethod
    def resolve_top_review_snippet(obj: Brand):
        review = top_review_for(obj)
        return excerpt(review.body) if review is not None else None


class BrandPageSchema(Schema):
    """Page-number envelope — identical shape to the DRF baseline (Req 11.1)."""

    count: int
    next: Optional[str]
    previous: Optional[str]
    results: List[BrandCardSchema]


class IndustrySchema(Schema):
    """Industry filter option for GET /api/industries/."""

    name: str
    slug: str
    brand_count: int


class ErrorSchema(Schema):
    """Error envelope: matches the baseline's ``{"detail": "..."}`` body."""

    detail: str
