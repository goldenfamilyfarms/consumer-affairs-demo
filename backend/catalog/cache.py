"""Cached lookups for small, rarely-changing reference data.

The industry set is tiny (a handful of rows) and changes about once a year, yet
``validate_industry`` is on the hot path for every filtered API request. Caching
the slug set turns that per-request ``SELECT ... EXISTS`` into an in-memory set
membership test.

Invalidation is signal-driven (see ``catalog.apps``): any Industry create/update/
delete clears the key. A TTL bounds staleness as a safety net — important because
the default ``LocMemCache`` is per-process, so signal invalidation only clears the
worker that handled the write; the TTL guarantees other workers converge. In a
multi-process deployment you'd point ``CACHES['default']`` at Redis/Memcached so
invalidation is shared and the TTL becomes belt-and-suspenders.
"""

from __future__ import annotations

from django.core.cache import cache

INDUSTRY_SLUGS_CACHE_KEY = "catalog:industry_slugs"
INDUSTRY_SLUGS_TTL = 3600  # seconds


def get_industry_slugs() -> frozenset[str]:
    """Return the set of valid industry slugs, cached with a TTL."""
    slugs = cache.get(INDUSTRY_SLUGS_CACHE_KEY)
    if slugs is None:
        # Imported lazily so this module is import-safe before apps are ready.
        from catalog.models import Industry

        slugs = frozenset(Industry.objects.values_list("slug", flat=True))
        cache.set(INDUSTRY_SLUGS_CACHE_KEY, slugs, INDUSTRY_SLUGS_TTL)
    return slugs


def clear_industry_slugs_cache(**kwargs) -> None:
    """Signal receiver: drop the cached slug set on any Industry change."""
    cache.delete(INDUSTRY_SLUGS_CACHE_KEY)
