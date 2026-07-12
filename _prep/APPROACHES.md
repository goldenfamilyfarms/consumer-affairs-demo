# Alternative Approaches — Branch Comparison

Two complete API implementations of the same challenge, on two branches, sharing
one domain layer. This exists to show I explored the design space and to keep the
"why this framework" conversation concrete in the live session.

| Branch | API framework | Migration source (default) |
|---|---|---|
| `approach/drf-sqldump` | Django REST Framework | `SqlDumpSource` (parses `db/dump.sql`) |
| `approach/ninja-api` | Django Ninja | `SqlDumpSource` (parses `db/dump.sql`) |

Both expose the **identical HTTP contract**: `GET /api/brands/` (page-number
envelope `{count, next, previous, results}`, `industry`/`sort`/`dir`/`page`/
`page_size` params, `400`/`404` semantics, the 8-field card) and
`GET /api/industries/`. The React frontend and the test suite are unchanged
across both branches.

---

## What stayed identical (the whole point)

The framework swap touched **only the web-adapter layer**. Reused verbatim:

- **Models** (`catalog/models.py`) — Industry/Brand/Review/Reviewer/ImportLedger, FK rules, indexes.
- **Computed rating** (`catalog/querysets.py` `with_stats()`) + the model property.
- **Importer** (`catalog/wp_import/`) — pluggable source, ledger idempotency, bulk writes.
- **The one-row top-review prefetch** — a correlated `Subquery(OuterRef(...)[:1])`.
- **Validation logic** — same allowlist rules (only the exception *type* differs).
- **The tests** — converted once to hit the endpoint via Django's test `Client` at literal paths, so they're framework-agnostic and pass against both.

On `approach/ninja-api` the shared query helpers live in `api/queries.py` with
**zero web-framework import** — that's the seam that made the swap cheap.

---

## What changed, file by file (DRF → Ninja)

| Concern | DRF (`approach/drf-sqldump`) | Ninja (`approach/ninja-api`) |
|---|---|---|
| Endpoint | `BrandListView(ListAPIView)` in `views.py` | `@api.get("/brands/")` function in `api.py` |
| Output shape | `BrandCardSerializer` (`serializers.Serializer`) | `BrandCardSchema` (Pydantic `Schema`) with `resolve_*` |
| Pagination | `BrandPagination(PageNumberPagination)` | hand-rolled `_paginate()` (same envelope) |
| Param validation | `ValidationError({"detail": ...})` → 400 | `HttpError(400, ...)` → `{"detail": ...}` |
| Routing | `api/urls.py` + `reverse("api:brand-list")` | `api.urls` mounted in `config/urls.py` |
| Shared queries | inline in serializer/view | extracted to `api/queries.py` (framework-free) |
| Dependency | `djangorestframework` | `django-ninja` (a library, not an installed app) |

---

## Trade-offs (defense talking points)

**Django REST Framework**
- ➕ Batteries included: pagination classes, filter/ordering backends, content negotiation, the browsable API, a huge ecosystem. The obvious default for a team already on DRF.
- ➕ Serializers double as input validators for write endpoints.
- ➖ More framework surface/ceremony; viewset indirection; serializers are Django-specific (not reusable outside the web layer).
- ➖ Runtime type checking, no schema-from-types.

**Django Ninja**
- ➕ Declarative Pydantic schemas = types *are* the contract; near-free OpenAPI/Swagger.
- ➕ Plain functions + explicit helpers → the domain logic naturally falls out of the web layer (see `queries.py`).
- ➕ Async-first; typically lighter/faster per request.
- ➖ Smaller ecosystem; you hand-roll things DRF gives you (I wrote `_paginate` myself).
- ➖ Pydantic v2 is a real dependency with its own learning curve; fewer off-the-shelf integrations.

**My call for *this* challenge:** DRF as the submitted baseline — its pagination/validation primitives map 1:1 onto the required contract with the least custom code, and it's the safer "senior default" for a reviewer. Ninja is the compelling alternative when the API is type-first, async matters, or you want OpenAPI for free — and building it proved the architecture's boundaries are clean (only the adapter changed).

---

## How to show it live

```bash
git checkout approach/drf-sqldump   # DRF version
cd backend && python -m pytest -q   # green

git checkout approach/ninja-api     # Ninja version
cd backend && python -m pytest -q   # same tests, still green
```

Same frontend, same contract, same tests — two frameworks. Diff `api/` between
the branches to show the swap is localized; diff `catalog/` to show it's untouched.
