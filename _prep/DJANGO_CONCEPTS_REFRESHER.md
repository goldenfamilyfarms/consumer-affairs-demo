# Django/DRF Concepts Refresher — for the Migration Demo

Scraped from the official docs (Django 6.0 + DRF) and mapped to exactly where
each concept shows up in this repo. Explanations are paraphrased for brevity;
follow the links for the authoritative text.

> Docs versions: Django resolves `/en/stable/` → **6.0**. DRF is the current
> release. Content was rephrased for compliance with licensing restrictions.

---

## 1. Aggregation — `annotate()`, `Avg`, `Count`, filtered aggregates

**What it is:** `aggregate()` collapses a queryset to summary values; `annotate()`
attaches a per-row computed value (e.g. a per-brand average) that you can then
filter, order, and serialize like any field. Aggregate functions (`Avg`, `Count`,
`Max`, …) accept a `filter=` argument so you can aggregate only a subset, and a
`default=` to control the empty-set result (otherwise `Avg` of nothing is `NULL`).

**In this repo:** `backend/catalog/querysets.py` → `BrandQuerySet.with_stats()`:
```python
self.annotate(
    review_count=Count("reviews", filter=QUALIFYING_REVIEW),
    computed_average_rating=Avg("reviews__rating", filter=QUALIFYING_REVIEW),
)
```
The `filter=Q(reviews__rating__gte=1)` is the "ratings below 1 don't count" rule;
`Avg` over no qualifying reviews yields `NULL` → the brand reports no rating.

**Talk track:** "The average is a database annotation, not Python — so it's
cheap, sortable, and consistent with the display."

Docs: <https://docs.djangoproject.com/en/stable/topics/db/aggregation/>

---

## 2. Query expressions — `F()`, `Subquery`, `OuterRef`

**What it is:**
- `F()` references a model field/annotation *in the database* so you compute
  without pulling values into Python.
- `Subquery(queryset)` embeds a correlated subquery; `OuterRef("field")` refers
  back to the outer query's row. The classic pattern is "one related row per
  parent": order a related queryset, take `.values("pk")[:1]`, wrap in `Subquery`.

**In this repo:** `backend/api/serializers.py` → `top_review_prefetch()`:
```python
top_id_per_brand = (
    Review.objects.filter(brand=OuterRef("brand"), rating__gte=1)
    .order_by("-rating", "-wp_post_date")
    .values("pk")[:1]
)
qs = Review.objects.filter(rating__gte=1, pk__in=Subquery(top_id_per_brand))
```
This pulls **exactly one** top review per brand — cross-DB (no `DISTINCT ON`).
`F()` is used in the view's ordering (see §4).

**Talk track:** "A correlated subquery picks the single winning review per brand,
so the prefetch is one row per brand, not thousands discarded."

Docs: <https://docs.djangoproject.com/en/stable/ref/models/expressions/>

---

## 3. `select_related` vs `prefetch_related` (and `Prefetch`)

**What it is:**
- `select_related(*fk_fields)` — follows **forward** FK/one-to-one via a SQL JOIN,
  one query. Use for single-valued relations (a brand's industry).
- `prefetch_related(*lookups)` — separate query per lookup, joined in Python.
  Use for multi-valued/reverse relations (a brand's reviews). A `Prefetch(...)`
  object lets you customize the prefetched queryset and stash it under `to_attr`.

**In this repo:** `backend/api/views.py` → `BrandListView.get_queryset()`:
```python
Brand.objects.with_stats()
    .select_related("industry")            # FK → JOIN
    .prefetch_related(top_review_prefetch())  # reverse → one extra query
```
Kills the N+1: a full page is the aggregate query + one prefetch, regardless of
page size.

Docs: <https://docs.djangoproject.com/en/stable/ref/models/querysets/#select-related>
and <https://docs.djangoproject.com/en/stable/ref/models/querysets/#prefetch-related>

---

## 4. Ordering — `order_by`, `F().desc(nulls_last=True)`, stable tiebreak

**What it is:** `order_by()` sorts at the DB. Wrapping a field in `F(...).asc()`/
`.desc()` lets you pass `nulls_last=True`/`nulls_first=True` to control where
NULLs land. Adding a unique tiebreak (e.g. `slug`) makes pagination deterministic.

**In this repo:** `BrandListView.get_queryset()`:
```python
order = F(sort_field)
ordering = order.asc(nulls_last=True) if direction == "asc" else order.desc(nulls_last=True)
return queryset.order_by(ordering, "slug")
```
Brands with a `NULL` average never crowd the top; the `slug` tiebreak stops rows
from shuffling across page boundaries.

Docs: <https://docs.djangoproject.com/en/stable/ref/models/expressions/#using-f-to-sort-null-values>

---

## 5. Bulk writes — `bulk_create`, `bulk_update`

**What it is:** `bulk_create(objs, batch_size=…, ignore_conflicts=…)` inserts many
rows in (generally) one query; `bulk_update(objs, fields, batch_size=…)` updates
given fields on many instances in ~one query. `batch_size` bounds statement size.
`ignore_conflicts=True` skips rows that violate a constraint instead of raising.

**In this repo:** `backend/catalog/wp_import/importer.py` — each `_upsert_*` phase
classifies rows into create/update/skip, then:
```python
Model.objects.bulk_create(to_create, batch_size=_BATCH)
Model.objects.bulk_update(to_update, FIELDS, batch_size=_BATCH)
```
So a phase is a bounded number of statements, not one per row — the scale story.

**Gotcha to know:** historically `bulk_create` didn't return PKs on all DBs; this
importer sidesteps that by rebuilding `{wp_id: pk}` maps with a fresh `SELECT`
between phases, so it never depends on bulk-assigned PKs.

Docs: <https://docs.djangoproject.com/en/stable/ref/models/querysets/#bulk-create>
and <https://docs.djangoproject.com/en/stable/ref/models/querysets/#bulk-update>

---

## 6. Transactions — `transaction.atomic()`

**What it is:** `atomic()` wraps a block so it commits as a unit or rolls back
entirely on exception. Usable as a decorator or context manager; nesting creates
savepoints.

**In this repo:** `importer.py` → `run_import()` wraps **each phase** in its own
`with transaction.atomic():`, so a mid-run failure rolls that phase back cleanly
and leaves the DB consistent.

Docs: <https://docs.djangoproject.com/en/stable/topics/db/transactions/>

---

## 7. `ForeignKey.on_delete`

**What it is:** the required policy for what happens to a row when the thing it
points at is deleted:
- **`CASCADE`** — delete this row too (emulates SQL `ON DELETE CASCADE`).
- **`PROTECT`** — block the delete, raising `ProtectedError`.
- **`SET_NULL`** — set the FK to `NULL` (requires `null=True`).
- (others: `RESTRICT`, `SET_DEFAULT`, `SET(...)`, `DO_NOTHING`.)

**In this repo:** `backend/catalog/models.py`:
- `Brand.industry` → `PROTECT` (can't orphan a brand by deleting its industry).
- `Review.brand` → `CASCADE` (reviews die with their brand).
- `Review.reviewer` → `SET_NULL, null=True` (attribution can be unknown).

Docs: <https://docs.djangoproject.com/en/stable/ref/models/fields/#django.db.models.ForeignKey.on_delete>

---

## 8. Custom Managers / `QuerySet.as_manager()`

**What it is:** `QuerySet.as_manager()` builds a Manager whose methods are copied
from a custom QuerySet — so your custom methods (like `with_stats()`) are
chainable *and* available as `Model.objects.with_stats()` without duplicating code
on both a Manager and a QuerySet.

**In this repo:** `models.py` → `Brand` sets `objects = BrandQuerySet.as_manager()`,
so `Brand.objects.with_stats()` works and stays chainable with `.filter()` etc.

Docs: <https://docs.djangoproject.com/en/stable/topics/db/managers/#creating-a-manager-with-queryset-methods>

---

## 9. Model `Meta.indexes`

**What it is:** declare composite/functional indexes in `Meta.indexes` with
`models.Index(fields=[...], name=...)`. Descending fields (`"-rating"`) create a
DESC index. Migrations create/drop them.

**In this repo:** `Review.Meta.indexes` (migration `0002`):
```python
models.Index(fields=["rating"], name="review_rating_idx")
models.Index(fields=["brand", "-rating", "-wp_post_date"], name="review_brand_top_idx")
```
The first speeds the `rating >= 1` filter on the hot path; the composite serves
the "top review per brand" access pattern and the per-brand aggregation.

Docs: <https://docs.djangoproject.com/en/stable/ref/models/indexes/>

---

## 10. Migrations

**What it is:** version-controlled schema changes. `makemigrations` diffs your
models into a migration file; `migrate` applies them; `sqlmigrate` shows the SQL;
`showmigrations` lists state.

**In this repo:** `catalog/migrations/0001_initial.py` (the schema) and
`0002_…_idx.py` (the two indexes). You'll run `migrate` in the demo setup.

Docs: <https://docs.djangoproject.com/en/stable/topics/migrations/>

---

## 11. Custom management commands — `BaseCommand`, `add_arguments`, `CommandError`

**What it is:** subclass `BaseCommand`, declare flags in `add_arguments(self, parser)`
(argparse), do the work in `handle(self, *args, **options)`. Raise `CommandError`
to fail with a message and a non-zero exit code; write output via `self.stdout`.

**In this repo:** `catalog/management/commands/import_wordpress.py` — `--source`
and `--dump-path` args; builds the chosen `WordPressSource`; raises `CommandError`
(non-zero exit, reason to stderr, no summary) on an unreadable source; prints the
per-model created/updated summary on success.

Docs: <https://docs.djangoproject.com/en/stable/howto/custom-management-commands/>

---

## 12. Signals — `post_save` / `post_delete`, `AppConfig.ready()`

**What it is:** a dispatcher that notifies receivers when events happen (e.g. a
model saved/deleted). Connect receivers in `AppConfig.ready()`. Use `dispatch_uid`
to prevent duplicate connections.

**In this repo:** `catalog/apps.py` → `CatalogConfig.ready()` connects
`clear_industry_slugs_cache` to `Industry`'s `post_save`/`post_delete`, so the
cached slug set (see §13) is invalidated whenever industries change.

**Caveat to know:** signals aren't a substitute for a transaction — a `post_save`
fires even if an outer transaction later rolls back. Fine here (cache bust), but
worth knowing.

Docs: <https://docs.djangoproject.com/en/stable/topics/signals/>

---

## 13. Cache framework — low-level API + LocMemCache

**What it is:** `from django.core.cache import cache` gives `get`/`set`/`delete`
(and `get_or_set`) for caching expensive computations. The default backend is
`LocMemCache`, which is **per-process** and thread-safe.

**In this repo:** `catalog/cache.py` → `get_industry_slugs()` caches the slug set
with a TTL, and `clear_industry_slugs_cache` deletes the key on Industry changes.

**The nuance for the live session:** because `LocMemCache` is per-process, signal
invalidation only clears the worker that handled the write — the TTL is the safety
net so other workers converge. Point `CACHES['default']` at Redis to share
invalidation across processes.

Docs: <https://docs.djangoproject.com/en/stable/topics/cache/#the-low-level-cache-api>
and <https://docs.djangoproject.com/en/stable/topics/cache/#local-memory-caching>

---

## 14. Templates — autoescaping, `|safe`, `|striptags`, custom filters

**What it is:** Django templates HTML-escape variables by default. `|safe` marks a
string as already-safe (no escaping) — dangerous for untrusted HTML. `|striptags`
removes tags (naively). A custom template filter lives in an app's
`templatetags/` module and is registered with `@register.filter`.

**In this repo:** `catalog/templatetags/catalog_extras.py` → `sanitize_html`
runs migrated WordPress HTML through **nh3** (an allowlist sanitizer) and marks the
result safe — so detail pages render real formatting but strip `<script>`,
event handlers, and `javascript:` URLs. Card excerpts use `|striptags` for
plain text.

**Why not just `|striptags` or `|safe`?** `striptags` is a text-level strip (fails
on malformed/nested markup and isn't a security boundary); `|safe` on untrusted
HTML is a stored-XSS vector. nh3 parses the DOM and enforces an allowlist.

Docs: <https://docs.djangoproject.com/en/stable/ref/templates/builtins/#std-templatefilter-safe>
and <https://docs.djangoproject.com/en/stable/howto/custom-template-tags/>

---

## 15. DRF — `ListAPIView` + `get_queryset`

**What it is:** DRF generic views wire a serializer + queryset to HTTP methods.
`ListAPIView` = read-only list endpoint. Override `get_queryset(self)` to build the
queryset per request (validation, filtering, ordering) and `serializer_class` for
the output shape.

**In this repo:** `backend/api/views.py` → `BrandListView(ListAPIView)` validates
params (via `api/filters.py`), then annotates/filters/orders in `get_queryset`;
`IndustryListView` backs `/api/industries/` (unpaginated).

Docs: <https://www.django-rest-framework.org/api-guide/generic-views/>

---

## 16. DRF — Serializers (plain `Serializer`, `SerializerMethodField`)

**What it is:** serializers convert querysets/instances to JSON (and validate
input). A plain `serializers.Serializer` declares fields explicitly (vs
`ModelSerializer` which derives them from a model). `SerializerMethodField` calls
`get_<field>()` for computed output.

**In this repo:** `api/serializers.py` → `BrandCardSerializer` is a plain
`Serializer` (the card shape is decoupled from the model) with method fields for
`industry`, `average_rating` (rounded), `short_description` (excerpt), and
`top_review_snippet`. `IndustrySerializer` is the small `{name, slug, brand_count}`.

**Defense note:** I chose plain `Serializer` over `ModelSerializer` because the
card is a *view model*, not a 1:1 mapping of the Brand table — I want the API
contract independent of the schema.

Docs: <https://www.django-rest-framework.org/api-guide/serializers/>
and <https://www.django-rest-framework.org/api-guide/fields/#serializermethodfield>

---

## 17. DRF — Pagination (`PageNumberPagination`)

**What it is:** DRF paginators wrap list responses. `PageNumberPagination` returns
`count`/`next`/`previous`/`results`; you set `page_size`, `page_size_query_param`
(to allow client override), and `max_page_size` (a cap — requests above it are
clamped, not rejected). An out-of-range page returns 404.

**In this repo:** `api/pagination.py` → `BrandPagination`:
```python
page_size = 12
page_query_param = "page"
page_size_query_param = "page_size"
max_page_size = 100
```
Matches the docs' `StandardResultsSetPagination` example almost exactly.

Docs: <https://www.django-rest-framework.org/api-guide/pagination/#pagenumberpagination>

---

## 18. DRF — Validation & error responses (`ValidationError` → 400)

**What it is:** raising `rest_framework.exceptions.ValidationError` (or returning a
`Response(status=400)`) produces a clean 400 with a JSON body. Validating params
before building the queryset keeps bad input from silently returning empty results.

**In this repo:** `api/filters.py` → `validate_industry` / `validate_sort` /
`validate_direction` raise `ValidationError({"detail": "..."})`; the view calls
them first in `get_queryset`. Unknown industry / bad sort / bad dir → 400; page out
of range → 404 (DRF default).

Docs: <https://www.django-rest-framework.org/api-guide/exceptions/#validationerror>

---

## Quick self-quiz (say the answer out loud)

1. Why `annotate` the average instead of a stored column? *(drift; source of truth)*
2. What makes `top_review_prefetch` one-row-per-brand? *(correlated `Subquery` + `OuterRef` + `[:1]`)*
3. `select_related` vs `prefetch_related` — which for `industry`, which for `reviews`? *(JOIN vs separate query)*
4. Why `nulls_last=True`? *(unrated brands don't top a rating sort)*
5. What does `bulk_create` not guarantee, and how does the importer avoid depending on it? *(PKs; rebuild id-maps via SELECT)*
6. Why one `atomic()` per phase, not one for the whole run? *(clean per-phase rollback in FK order)*
7. `PROTECT` vs `CASCADE` vs `SET_NULL` — which FK gets which and why?
8. Why `QuerySet.as_manager()`? *(no duplicated methods; chainable + on manager)*
9. Where is the industry-slug cache invalidated, and what's the multi-process caveat? *(signals in `ready()`; LocMem is per-process → TTL/Redis)*
10. Why `sanitize_html` (nh3) and not `|safe` or `|striptags`? *(allowlist DOM sanitizer vs XSS vector / naive strip)*
11. Why a plain `Serializer` instead of `ModelSerializer`? *(card is a view model, contract decoupled from schema)*
12. What does `max_page_size` do to an over-cap request? *(clamps, doesn't 400)*
