# Walkthrough: `backend/api/` — the brand-listing REST endpoint

This folder is the whole public API. It's small on purpose — one real endpoint
(`GET /api/brands/`) plus a little helper endpoint (`GET /api/industries/`). The
job is: *take the clean relational data the importer produced, and serve it as
brand "cards" the React app can render — filtered, sorted, and paginated, with
everything computed in the database.*

The guiding rule here is **do the work in the database, validate before you
touch it, and keep the wire contract stable.** Let me walk the files.

```
views.py        →  the endpoint(s): build the queryset, hand it to the serializer
serializers.py  →  the card shape + the "top review" rule
filters.py      →  validate industry / sort / dir params (fail fast with 400)
pagination.py   →  the page-number envelope {count, next, previous, results}
urls.py         →  wires the paths
```

---

## `views.py` — where a request becomes a queryset

The star is `BrandListView`, a DRF `ListAPIView`. The interesting method is
`get_queryset` — and the order of operations matters:

1. **Validate first, before any DB work.** It runs the three validators from
   `filters.py` on the incoming params. If the industry slug is unknown, or the
   sort key / direction is bogus, we bail out with a clean `400` *before*
   building any query. No silent empty results.
2. **Build the annotated queryset:**
   ```python
   Brand.objects.with_stats()
       .select_related("industry")
       .prefetch_related(top_review_prefetch())
   ```
   - `with_stats()` (defined over on the model's queryset) annotates
     `review_count` and `computed_average_rating` *in the database*.
   - `select_related("industry")` grabs the industry in the same query (it's a
     forward foreign key), so rendering the industry name doesn't cost a query
     per row.
   - `prefetch_related(top_review_prefetch())` pulls exactly one "top review"
     per brand in a single extra query (more on that below).
3. **Filter** by industry slug if one was given.
4. **Order** on the annotation, with a nice production detail:
   ```python
   order = F(sort_field)
   ordering = order.desc(nulls_last=True)  # or .asc(...)
   return queryset.order_by(ordering, "slug")
   ```
   `nulls_last=True` keeps brands with no rating from crowding the top of a
   rating sort, and the `"slug"` tiebreak makes pagination deterministic (rows
   won't shuffle between pages when two brands tie).

Net result: rendering a full page of cards is basically **two queries** — the
annotated brand query and the one top-review prefetch — no matter how many
brands or reviews exist. That's the N+1 story.

`IndustryListView` is the tiny sibling: it returns every industry (name, slug,
and a `brand_count` annotation) as a plain unpaginated list, so the React filter
dropdown can load the full set of industries on its own instead of guessing from
whatever brands happen to be on the current page.

> Interview one-liner: *"Validate params, then annotate/filter/order in the DB;
> select_related the industry and prefetch one top review per brand, so a page is
> a constant couple of queries with nulls sorted last and a stable tiebreak."*

---

## `serializers.py` — the card shape and the "top review" trick

`BrandCardSerializer` defines exactly what a card looks like on the wire:

```
name, slug, industry, industry_slug, average_rating,
review_count, short_description, top_review_snippet
```

A few deliberate choices:

- It's a **plain `Serializer`, not a `ModelSerializer`.** The card is a *view
  model* — it doesn't map 1:1 to the Brand table (it flattens the industry to a
  name, rounds the rating, excerpts the body). Keeping it a plain serializer
  means the API contract isn't chained to the database schema.
- **`industry` vs `industry_slug`.** The human-readable name is for display; the
  slug is the value the React filter round-trips back to the API. Exposing both
  means the frontend never has to guess or reverse-map.
- **`average_rating`** is the computed annotation, rounded to two decimals, or
  `null` when there are no qualifying reviews.
- **`short_description`** and **`top_review_snippet`** run through the `excerpt`
  helper, which strips HTML tags, unescapes entities, and cuts on a word
  boundary at ~160 chars — so cards show clean plain text, not raw `<p>` markup.

### The `top_review_prefetch()` bit is the clever one

The "top review" rule is: highest rating that's ≥ 1, ties broken by the most
recent date. The naive way would be to prefetch *all* a brand's reviews ordered
best-first and read index 0 — but that drags every review into memory just to
throw all but one away. Instead:

```python
top_id_per_brand = (
    Review.objects.filter(brand=OuterRef("brand"), rating__gte=1)
    .order_by("-rating", "-wp_post_date")
    .values("pk")[:1]
)
qs = Review.objects.filter(rating__gte=1, pk__in=Subquery(top_id_per_brand))
return Prefetch("reviews", queryset=qs, to_attr="_top_review_cache")
```

That correlated subquery picks the single winning review id *per brand*, so the
prefetch returns one row per brand — in one query, and it works on both SQLite
and Postgres (no `DISTINCT ON` dependency). The serializer just reads
`brand._top_review_cache[0]` (with a direct-query fallback for single-object use
outside the list view).

> Interview one-liner: *"Plain serializer because the card is a view model; the
> top review is one row per brand via a correlated Subquery, not a prefetch-all-
> and-discard."*

---

## `filters.py` — validate up front, 400 on junk

Three little functions: `validate_industry`, `validate_sort`, `validate_direction`.
They all follow the same pattern — if the value is missing, apply a default; if
it's present but bogus, raise DRF's `ValidationError({"detail": ...})`, which
becomes a clean `400`.

Two things worth calling out:

- **The sort allow-list is decoupled from column names.** The public value is
  `avg_rating` / `review_count`; internally that maps to the annotation names
  (`computed_average_rating` / `review_count`). So we can rename the annotation
  without breaking the API contract, and an unknown sort is a real 400 instead
  of a silent no-op.
- **Industry validation uses a cached slug set.** Instead of a
  `SELECT ... EXISTS` on every filtered request, `validate_industry` checks
  membership against `get_industry_slugs()` (from `catalog/cache.py`), which
  caches the tiny slug set and is invalidated by a signal whenever an industry
  changes. The one caveat — and a good thing to mention live — is that the
  default local-memory cache is per-process, so in a multi-worker deployment the
  TTL is the safety net and you'd point the cache at Redis to share invalidation.

> Interview one-liner: *"Validation runs before the queryset so bad input is a
> clean 400 with a message; the sort allow-list keeps the public contract off the
> column names; industry lookup is a cached set membership, not a per-request
> query."*

---

## `pagination.py` — the envelope

`BrandPagination` subclasses DRF's `PageNumberPagination`:

```python
page_size = 12
page_query_param = "page"
page_size_query_param = "page_size"
max_page_size = 100
```

So responses come back as `{count, next, previous, results}`. Chosen over
limit/offset because the React control and a future mobile client both think in
"pages," and `count` lets the UI show "N brands." `next`/`previous` are absolute
URLs so a client can just follow them. `page_size` is client-controllable but
capped at 100 — a request above the cap gets **clamped** (DRF's standard
behavior), not rejected. An out-of-range page number returns `404`, which is
DRF's default and exactly what the contract promises.

> Interview one-liner: *"Page-number pagination because clients think in pages and
> count enables 'showing N'; page_size is capped and clamped, out-of-range is a
> 404."*

---

## `urls.py`

Just wires the two views to their paths under `api:` — `brands/` →
`BrandListView` and `industries/` → `IndustryListView`. The root URLconf mounts
this whole module under `/api/`.

---

## `tests/`

- **`test_api_contract.py`** — example-based: the envelope shape, the exact card
  fields, filtering by each slug, both sorts × both directions, default/explicit
  page sizes, the 400s and the 404, and the zero-review row shape.
- **`test_api_properties.py`** — Hypothesis property tests: pagination invariants
  (pages concatenate to the full set, no gaps/dupes), sort monotonicity with
  nulls last, filter soundness, and the top-review rule.
- **`test_industries.py`** — the industries endpoint: sorted, with brand counts,
  and the exact row shape.

---

## TL;DR

- `views.py` — validate → annotate/filter/order in the DB → serialize; ~2 queries per page.
- `serializers.py` — the card view-model + a one-row-per-brand top-review subquery.
- `filters.py` — fail-fast 400 validation; cached industry-slug lookup.
- `pagination.py` — page-number envelope, capped page size, 404 out of range.

One sentence: **all the filtering, sorting, and aggregation happens in the
database; the view just validates, and the serializer just shapes.**

> Note: this describes the DRF implementation on `approach/drf-sqldump`. The
> `approach/ninja-api` branch swaps this same contract to Django Ninja — same
> endpoints, same envelope, same 400/404s — see `_prep/APPROACHES.md`.
