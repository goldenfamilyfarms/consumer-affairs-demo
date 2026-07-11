"""Idempotent upsert orchestration for the WordPress import.

This module implements the core import logic per the design's flowchart:

    source record K → live row with K exists? → update fields
                    → else ledger has K?       → skip (deletion preserved)
                    → else                     → create row + ledger entry

Each phase (Industries → Reviewers → Brands → Reviews) runs inside a single
``transaction.atomic()`` block. FK resolution uses pre-built ``{wp_id: pk}``
maps so no per-row queries are needed.

Scale: each phase classifies its source rows into create / update / skip, then
writes them with ``bulk_create`` / ``bulk_update`` in chunks — so a phase costs
a bounded number of statements regardless of row count, not one per row. The
per-phase ``existing`` map is a single ``SELECT``; the ledger check is a set
membership test.

The importer is source-agnostic: it accepts any :class:`WordPressSource`
instance and returns per-model created/updated counts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Set

from django.db import transaction

from catalog.models import Brand, ImportLedger, Industry, Review, Reviewer
from catalog.wp_import.sources import WordPressSource

logger = logging.getLogger(__name__)

__all__ = ["run_import", "ImportSummary"]

# Chunk size for bulk writes — bounds statement/parameter size per round trip.
_BATCH = 1000


# --------------------------------------------------------------------------- #
# Summary dataclass
# --------------------------------------------------------------------------- #


@dataclass
class ImportSummary:
    """Per-model counts from a completed import run."""

    industries_created: int = 0
    industries_updated: int = 0
    reviewers_created: int = 0
    reviewers_updated: int = 0
    brands_created: int = 0
    brands_updated: int = 0
    reviews_created: int = 0
    reviews_updated: int = 0

    def as_dict(self) -> Dict[str, Dict[str, int]]:
        return {
            "industries": {
                "created": self.industries_created,
                "updated": self.industries_updated,
            },
            "reviewers": {
                "created": self.reviewers_created,
                "updated": self.reviewers_updated,
            },
            "brands": {
                "created": self.brands_created,
                "updated": self.brands_updated,
            },
            "reviews": {
                "created": self.reviews_created,
                "updated": self.reviews_updated,
            },
        }


# --------------------------------------------------------------------------- #
# Ledger helpers
# --------------------------------------------------------------------------- #


def _load_ledger_keys(model_label: str) -> Set[int]:
    """Load the set of wp_ids the ledger has for a given model label."""
    return set(
        ImportLedger.objects.filter(model_label=model_label).values_list(
            "wp_id", flat=True
        )
    )


def _record_in_ledger(model_label: str, wp_ids: List[int]) -> None:
    """Bulk-insert ledger entries for newly created rows.

    ``ignore_conflicts`` guards the unique_together so a partial prior run can't
    raise on a key that's already recorded.
    """
    if not wp_ids:
        return
    ImportLedger.objects.bulk_create(
        [ImportLedger(model_label=model_label, wp_id=wp_id) for wp_id in wp_ids],
        batch_size=_BATCH,
        ignore_conflicts=True,
    )


# --------------------------------------------------------------------------- #
# Phase: Industries
# --------------------------------------------------------------------------- #


def _upsert_industries(source: WordPressSource) -> tuple[int, int]:
    """Upsert industries. Returns (created_count, updated_count)."""
    model_label = "industry"
    ledger_keys = _load_ledger_keys(model_label)
    existing: Dict[int, Industry] = {
        ind.wp_term_id: ind for ind in Industry.objects.all()
    }

    to_create: List[Industry] = []
    to_update: List[Industry] = []

    for src in source.industries():
        wp_id = src.wp_term_id
        live = existing.get(wp_id)
        if live is not None:
            changed = False
            if live.name != src.name:
                live.name = src.name
                changed = True
            if live.slug != src.slug:
                live.slug = src.slug
                changed = True
            if changed:
                to_update.append(live)
        elif wp_id in ledger_keys:
            pass  # previously imported, since deleted — preserve deletion
        else:
            to_create.append(
                Industry(wp_term_id=wp_id, name=src.name, slug=src.slug)
            )

    if to_create:
        Industry.objects.bulk_create(to_create, batch_size=_BATCH)
        _record_in_ledger(model_label, [o.wp_term_id for o in to_create])
    if to_update:
        Industry.objects.bulk_update(to_update, ["name", "slug"], batch_size=_BATCH)

    return len(to_create), len(to_update)


# --------------------------------------------------------------------------- #
# Phase: Reviewers
# --------------------------------------------------------------------------- #


def _referenced_author_ids(source: WordPressSource) -> Set[int]:
    """Collect the distinct ``post_author`` wp_user_ids referenced by reviews.

    Per Requirement 4.1 the import creates a Reviewer only for WordPress users
    referenced as a review ``post_author`` — not for every ``wp_users`` row.
    """
    return {src.wp_user_id for src in source.reviews() if src.wp_user_id is not None}


def _upsert_reviewers(
    source: WordPressSource,
    referenced_author_ids: Set[int],
) -> tuple[int, int]:
    """Upsert reviewers referenced as review authors. Returns (created, updated)."""
    model_label = "reviewer"
    ledger_keys = _load_ledger_keys(model_label)
    existing: Dict[int, Reviewer] = {r.wp_user_id: r for r in Reviewer.objects.all()}

    to_create: List[Reviewer] = []
    to_update: List[Reviewer] = []

    for src in source.users():
        wp_id = src.wp_user_id
        if wp_id not in referenced_author_ids:
            continue  # only import users referenced as a review author (Req 4.1)
        live = existing.get(wp_id)
        if live is not None:
            changed = False
            if live.display_name != src.display_name:
                live.display_name = src.display_name
                changed = True
            if live.wp_user_login != src.user_login:
                live.wp_user_login = src.user_login
                changed = True
            if live.email != src.email:
                live.email = src.email
                changed = True
            if changed:
                to_update.append(live)
        elif wp_id in ledger_keys:
            pass
        else:
            to_create.append(
                Reviewer(
                    wp_user_id=wp_id,
                    display_name=src.display_name,
                    wp_user_login=src.user_login,
                    email=src.email,
                )
            )

    if to_create:
        Reviewer.objects.bulk_create(to_create, batch_size=_BATCH)
        _record_in_ledger(model_label, [o.wp_user_id for o in to_create])
    if to_update:
        Reviewer.objects.bulk_update(
            to_update, ["display_name", "wp_user_login", "email"], batch_size=_BATCH
        )

    return len(to_create), len(to_update)


# --------------------------------------------------------------------------- #
# Phase: Brands
# --------------------------------------------------------------------------- #

_BRAND_FIELDS = [
    "name",
    "slug",
    "body",
    "website_url",
    "founded_year",
    "headquarters",
    "migrated_average_rating",
    "seo_title",
    "seo_metadesc",
    "industry_id",
    "wp_post_date",
]


def _upsert_brands(
    source: WordPressSource,
    industry_map: Dict[int, int],
) -> tuple[int, int]:
    """Upsert brands. ``industry_map`` is ``{wp_term_id: Industry.pk}``."""
    model_label = "brand"
    ledger_keys = _load_ledger_keys(model_label)
    existing: Dict[int, Brand] = {b.wp_post_id: b for b in Brand.objects.all()}

    to_create: List[Brand] = []
    to_update: List[Brand] = []

    for src in source.brands():
        wp_id = src.wp_post_id

        industry_pk = (
            industry_map.get(src.industry_wp_term_id)
            if src.industry_wp_term_id is not None
            else None
        )
        if industry_pk is None:
            logger.warning(
                "Brand wp_post_id=%d has no resolvable industry (wp_term_id=%s), skipping.",
                wp_id,
                src.industry_wp_term_id,
            )
            continue

        live = existing.get(wp_id)
        if live is not None:
            values = {
                "name": src.name,
                "slug": src.slug,
                "body": src.body,
                "website_url": src.website_url,
                "founded_year": src.founded_year,
                "headquarters": src.headquarters,
                "migrated_average_rating": src.average_rating,
                "seo_title": src.seo_title,
                "seo_metadesc": src.seo_metadesc,
                "industry_id": industry_pk,
                "wp_post_date": src.wp_post_date,
            }
            if any(getattr(live, field) != value for field, value in values.items()):
                for field, value in values.items():
                    setattr(live, field, value)
                to_update.append(live)
        elif wp_id in ledger_keys:
            pass
        else:
            to_create.append(
                Brand(
                    wp_post_id=wp_id,
                    name=src.name,
                    slug=src.slug,
                    body=src.body,
                    website_url=src.website_url,
                    founded_year=src.founded_year,
                    headquarters=src.headquarters,
                    migrated_average_rating=src.average_rating,
                    seo_title=src.seo_title,
                    seo_metadesc=src.seo_metadesc,
                    industry_id=industry_pk,
                    wp_post_date=src.wp_post_date,
                )
            )

    if to_create:
        Brand.objects.bulk_create(to_create, batch_size=_BATCH)
        _record_in_ledger(model_label, [o.wp_post_id for o in to_create])
    if to_update:
        Brand.objects.bulk_update(to_update, _BRAND_FIELDS, batch_size=_BATCH)

    return len(to_create), len(to_update)


# --------------------------------------------------------------------------- #
# Phase: Reviews
# --------------------------------------------------------------------------- #

_REVIEW_FIELDS = [
    "title",
    "slug",
    "body",
    "rating",
    "reviewer_name",
    "reviewer_location",
    "brand_id",
    "reviewer_id",
    "wp_post_date",
]


def _upsert_reviews(
    source: WordPressSource,
    brand_map: Dict[int, int],
    reviewer_map: Dict[int, int],
) -> tuple[int, int]:
    """Upsert reviews. ``brand_map``/``reviewer_map`` resolve FKs by wp id."""
    model_label = "review"
    ledger_keys = _load_ledger_keys(model_label)
    existing: Dict[int, Review] = {r.wp_post_id: r for r in Review.objects.all()}

    to_create: List[Review] = []
    to_update: List[Review] = []

    for src in source.reviews():
        wp_id = src.wp_post_id

        brand_pk = (
            brand_map.get(src.brand_wp_post_id)
            if src.brand_wp_post_id is not None
            else None
        )
        if brand_pk is None:
            logger.warning(
                "Review wp_post_id=%d has no resolvable brand (brand_wp_post_id=%s), skipping.",
                wp_id,
                src.brand_wp_post_id,
            )
            continue

        reviewer_pk = (
            reviewer_map.get(src.wp_user_id) if src.wp_user_id is not None else None
        )

        live = existing.get(wp_id)
        if live is not None:
            values = {
                "title": src.title,
                "slug": src.slug,
                "body": src.body,
                "rating": src.rating,
                "reviewer_name": src.reviewer_name,
                "reviewer_location": src.reviewer_location,
                "brand_id": brand_pk,
                "reviewer_id": reviewer_pk,
                "wp_post_date": src.wp_post_date,
            }
            if any(getattr(live, field) != value for field, value in values.items()):
                for field, value in values.items():
                    setattr(live, field, value)
                to_update.append(live)
        elif wp_id in ledger_keys:
            pass
        else:
            to_create.append(
                Review(
                    wp_post_id=wp_id,
                    title=src.title,
                    slug=src.slug,
                    body=src.body,
                    rating=src.rating,
                    reviewer_name=src.reviewer_name,
                    reviewer_location=src.reviewer_location,
                    brand_id=brand_pk,
                    reviewer_id=reviewer_pk,
                    wp_post_date=src.wp_post_date,
                )
            )

    if to_create:
        Review.objects.bulk_create(to_create, batch_size=_BATCH)
        _record_in_ledger(model_label, [o.wp_post_id for o in to_create])
    if to_update:
        Review.objects.bulk_update(to_update, _REVIEW_FIELDS, batch_size=_BATCH)

    return len(to_create), len(to_update)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


def run_import(source: WordPressSource) -> ImportSummary:
    """Run a full idempotent import from the given source.

    Phases execute in FK dependency order, each inside its own
    ``transaction.atomic()`` block so a mid-run failure rolls back cleanly.
    Returns an :class:`ImportSummary` with per-model created/updated counts.
    """
    summary = ImportSummary()

    # Phase 1: Industries
    with transaction.atomic():
        ic, iu = _upsert_industries(source)
        summary.industries_created = ic
        summary.industries_updated = iu

    # Phase 2: Reviewers — only users referenced as review authors (Req 4.1).
    referenced_author_ids = _referenced_author_ids(source)
    with transaction.atomic():
        rc, ru = _upsert_reviewers(source, referenced_author_ids)
        summary.reviewers_created = rc
        summary.reviewers_updated = ru

    # FK resolution maps (rebuilt after each dependency phase commits).
    industry_map: Dict[int, int] = dict(
        Industry.objects.values_list("wp_term_id", "pk")
    )
    reviewer_map: Dict[int, int] = dict(
        Reviewer.objects.values_list("wp_user_id", "pk")
    )

    # Phase 3: Brands
    with transaction.atomic():
        bc, bu = _upsert_brands(source, industry_map)
        summary.brands_created = bc
        summary.brands_updated = bu

    brand_map: Dict[int, int] = dict(Brand.objects.values_list("wp_post_id", "pk"))

    # Phase 4: Reviews
    with transaction.atomic():
        rvc, rvu = _upsert_reviews(source, brand_map, reviewer_map)
        summary.reviews_created = rvc
        summary.reviews_updated = rvu

    return summary
