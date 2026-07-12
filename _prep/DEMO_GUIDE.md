# WP → Django Migration — Demo & Defense Guide

A speaking script and prep pack for the live session. Structure mirrors the
challenge: **walk through what you built (~5 min) → defend decisions (~10 min)
→ design a new requirement together (~10–15 min).**

> How to use this: the **▶ SAY** blocks are things you can say close to
> verbatim. The **DO** blocks are what to click/run. The **PROBE / ANSWER**
> blocks are anticipated questions with crisp answers. Practice the 5-minute
> walkthrough once out loud; skim everything else.

---

## 0. Pre-demo setup (do this 10 minutes before the call)

Two terminals, plus a browser. The WordPress/Docker stack is **not** needed —
the import reads the committed `db/dump.sql`.

**Fastest path (Makefile):** `make setup` once, then `make backend` and
`make frontend` in two terminals (or `make dev` to run both; `make stop` ends
the background Django). `make test` runs both suites. `make help` lists
everything. The manual commands below are the equivalent if you prefer them.

**Terminal 1 — backend**
```bash
# from repo root
python -m venv .venv                       # if not already created
.venv\Scripts\activate                     # Windows  (source .venv/bin/activate on mac/linux)
pip install -r backend/requirements.txt
cd backend
python manage.py migrate
python manage.py import_wordpress
python manage.py runserver                 # http://127.0.0.1:8000
```

**Terminal 2 — frontend**
```bash
cd frontend
npm install
npm run dev                                # http://localhost:5173
```

**Browser tabs to pre-open:**
1. http://localhost:5173/ — the React app (main event)
2. http://127.0.0.1:8000/ — the SSR homepage
3. http://127.0.0.1:8000/api/brands/?sort=avg_rating&dir=desc — the API (DRF browsable)
4. Editor open at the repo root

**Pre-flight checklist (run once, confirm green):**
```bash
cd backend && python -m pytest -q            # expect: 78 passed
cd ../frontend && npm test                   # expect: 45 passed
```

**Reset-to-clean (if you want a pristine DB before demoing the migration):**
```bash
cd backend && del db.sqlite3 && python manage.py migrate && python manage.py import_wordpress
```

**Key numbers to have in your head:** 5 industries, 5 brands, 60 reviews (12/brand),
8 reviewers. 78 backend tests, 45 frontend tests, 11 formal correctness properties.

---

## 1. The 30-second framing (open with this)

▶ **SAY:** "The task was to replace a WordPress consumer-reviews site with a
Django app plus a production React component and an SCSS source tree. WordPress
stores everything in the denormalized `wp_posts`/`wp_postmeta` shape across two
custom post types — `brand` and `review` — one `industry` taxonomy, ACF fields,
and Yoast metadata. My north star was: *don't reproduce WordPress's shape —
model the domain cleanly, and make the migration re-runnable and defensible.*
I'll show it working, then walk the architecture, and I've got opinions on the
trade-offs."

---

## 2. The 5-minute demo walkthrough (what to click, what to say)

Go **outside-in**: show the product working first, then the code. Interviewers
want to see it run before they see it explained.
---

## 6. Hard challenges & honest answers (volunteer these — it reads as senior)

Senior signal = knowing your own trade-offs before they point them out. Keep a running "with more time I'd…" list.

- **"The whole thing is unauthenticated."** "Correct and intentional — it's a public, read-only brand listing, which matches the WP site it replaces. The moment anything mutating or user-specific is added, it needs auth and per-object permissions. I flagged that in the README rather than silently shipping an open write path."
- **"You render migrated HTML with `|safe`."** "Through `nh3`, an allowlist sanitizer, at render time — so `<script>`, event handlers, and `javascript:` URLs are stripped even if a row is tampered with. Card excerpts go further and strip tags entirely to plain text."
- **"SQLite in dev."** "Dev convenience; the ORM code is Postgres-ready. The only place engine matters is the aggregate/annotation path, which is standard SQL. I'd run Postgres in CI and prod."
- **"Pagination never shows with 5 brands."** "Right — with a page size of 12 there's one page. The control is built and tested; it just correctly hides when everything fits. I can drop the page size live to show it."
- **"Your `industry` filter originally sent the name, not the slug."** *(If it comes up.)* "I caught that — the card now exposes `industry_slug` and the filter round-trips on the slug, matching the API contract. There's a contract test asserting the exact field set."
- **"The top-review snippet has a fallback query."** "The serializer prefers the prefetched top review, but falls back to a single query if the prefetch wasn't applied — that's for single-object/test use. The list view always applies the prefetch, so there's no N+1 in the hot path."
- **"React StrictMode double-fetches in dev."** "Expected — StrictMode double-invokes effects in dev to surface unsafe effects. My fetch is abortable and idempotent, so it's harmless; it doesn't happen in production builds."

**Your "with more time" list (say it proactively):**
1. Batch the importer with `bulk_create`/`bulk_update` for genuine 100x volume.
2. Add `page` to the URL and cursor pagination as an option for mobile infinite-scroll.
3. Cache or precompute the rating/top-review if read volume grew.
4. A CI pipeline running both suites + Lighthouse; Postgres in CI.
5. Multi-select industry filter if the product wanted it.

---

## 7. Property-based testing — the differentiator (be ready to explain it)

> **SAY:** "Instead of only example tests, I encoded the *invariants* the system must always uphold and let Hypothesis generate hundreds of cases. For instance: 'running the import twice leaves counts and every field identical' — that property is what caught the naive-datetime bug. Others: the computed average always equals the mean of ratings ≥ 1 and is null iff none qualify; the property and the DB annotation always agree; reviewer de-duplication; slug uniqueness; pagination invariants (pages concatenate to the full set with no gaps or dupes); sort monotonicity with nulls last; filter soundness."

- **PROBE — "What's the value over example tests?"** "Example tests check the cases I thought of. Property tests attack the cases I didn't — they generate adversarial inputs against a stated invariant. That's how the timezone bug surfaced: no example I'd have hand-written exercised it, but 'idempotent re-run' as a property did."

---

## 8. The live "new requirement" — a framework + worked examples

They'll hand you a fresh requirement and watch how you *drive the AI* and reason. Process beats speed.

### The framework (say it out loud as you work)

1. **Clarify scope first.** "Before I write anything — is this read-only or does it mutate? Does it need to be in the API contract, the SSR pages, or both? What's the expected data volume?" One or two sharp questions signal seniority.
2. **Locate the seam.** Name the layer it touches: model, importer, queryset, serializer/view, or component. Most changes are one layer deep by design.
3. **State the contract change** (if any) before coding — new param, new field, new status code.
4. **Brief the AI narrowly.** "Add a validated `min_rating` query param to `BrandListView`, mapped through the existing `filters.py` allowlist pattern; 400 on non-numeric; add a contract test." Then *read* the output against your mental model, don't rubber-stamp it.
5. **Say what you'd test** — ideally the invariant, not just an example.

### Worked example A — "Filter brands by minimum average rating"

> **SAY:** "That's a Pillar-2 change, one layer deep. In `filters.py` I add a `validate_min_rating` that parses a float in [1,5] and 400s otherwise, matching the existing validator style. In `BrandListView` I apply `.filter(computed_average_rating__gte=value)` on the annotated queryset — note it has to be after `with_stats()` since it's an annotation. Contract: new optional `min_rating` param. Test: a property that every returned row's rating ≥ the requested floor, plus a 400 for junk input. No model or migration change."

### Worked example B — "Multi-select industry filter"

> **SAY:** "Contract change: `industry` accepts a comma-separated list of slugs. Validator switches from 'is this a slug' to 'are all of these slugs'; the queryset uses `industry__slug__in=[...]`. On the React side, `FilterControl` becomes a group of checkboxes or a multi-select, and `useUrlSyncedFilters` serializes a list into the query string — the URL stays the source of truth. I'd keep the single-value path working for back-compat. Test: filter soundness generalizes — every row's industry is in the requested set."

### Worked example C — "Add review submission"

> **SAY:** "This is the big one because it crosses from read-only into mutation, so I'd flag scope immediately: now we need auth, input validation, spam/rate-limiting, and a write endpoint. Model already supports it — a `Review` with a nullable reviewer and a required brand FK. I'd add a `POST /api/brands/<slug>/reviews/` with a write serializer that validates rating 1–5 and body length, require authentication, and think about idempotency/duplicate submission. I would *not* let this reuse the read serializer. And I'd call out that this invalidates any cached average — which is an argument for keeping the average computed, not stored."

### Worked example D — "Full-text search over brands/reviews"

> **SAY:** "For this data size, a Postgres `SearchVector`/`SearchRank` on brand name + body is the right first step — no new infrastructure. Contract: a `q` param, validated and length-capped. If it grew, I'd move to a dedicated engine (OpenSearch), but I wouldn't start there. Test: results contain the term; empty query is a no-op, not an error."

### If AI produces something you don't like on the call

> **SAY:** "I'd push back here — this reaches into the model when it only needs a queryset change," or "this swallows the error; I want an explicit 400 with a message to match the rest of the API." Narrate the *why*. They're grading your judgment, not the AI's output.

---

## 9. Quick-reference cheat sheet

**Commands**
```bash
# Backend
cd backend
python manage.py migrate
python manage.py import_wordpress            # --source=dump|mariadb  --dump-path=...
python manage.py runserver 8000
python -m pytest -q                          # 78 passed

# Frontend
cd frontend
npm run dev                                  # localhost:5173
npm test                                     # 45 passed
npx sass scss/main.scss static/css/theme.css # recompile CSS
```

**Numbers:** 5 industries · 5 brands · 60 reviews (12/brand) · 8 reviewers · 78 backend tests · 45 frontend tests · default page size 12.

**Where things live**
| Concern | File |
|---|---|
| Models + natural keys + FK rules | `backend/catalog/models.py` |
| Computed rating (annotation + property) | `backend/catalog/querysets.py` |
| Source interface + dump/MariaDB readers | `backend/catalog/wp_import/sources.py` |
| SQL dump tokenizer | `backend/catalog/wp_import/dump_parser.py` |
| Idempotent upsert + ledger | `backend/catalog/wp_import/importer.py` |
| Import command | `backend/catalog/management/commands/import_wordpress.py` |
| Card serializer + top-review rule | `backend/api/serializers.py` |
| List view / pagination / validation | `backend/api/{views,pagination,filters}.py` |
| SSR views + permalink URLs | `backend/catalog/{views,urls}.py` |
| HTML sanitizer filter | `backend/catalog/templatetags/catalog_extras.py` |
| Component | `frontend/src/components/BrandList/BrandList.jsx` |
| State hooks | `frontend/src/hooks/{useBrands,useUrlSyncedFilters}.js` |
| SCSS tokens + entry | `frontend/scss/abstracts/_tokens.scss`, `frontend/scss/main.scss` |

**One-line answers to keep in your pocket**
- *Why compute the average?* Reviews are the source of truth; a stored aggregate drifts.
- *Why the ledger?* To tell "new" from "deleted on purpose" so re-import never resurrects deletions.
- *Why slug filtering?* Stable, URL-safe, round-trips between the React URL and the API.
- *Why the URL as state?* Shareable, back-button friendly, no extra state library.
- *Why a source protocol?* Isolates *where* content comes from from *how* it's upserted; it's the scaling seam.

---

## 10. Closing line

> **SAY:** "The theme running through all of it: model the domain honestly, make the boundaries pluggable, keep the invariants executable, and let the URL and the database do the work instead of piling state into the client. I'm happy to go deeper on any layer or take a new requirement."

### Beat 1 — The React `<BrandList />` (the headline) · ~90s
**DO:** Open http://localhost:5173/.
▶ **SAY:** "This is the production React component. It's server-agnostic — it
talks to a single REST endpoint. Note the page chrome matches the migrated
theme: header, hero, footer, all from the same design tokens."

**DO:** Change **Sort by → "Highest rated."**
▶ **SAY:** "Sorting happens in the database, not the client. Watch the URL —
`?sort=avg_rating&dir=desc`. The URL is my single source of truth for filter and
sort state, so this view is shareable, bookmarkable, and back-button friendly."

**DO:** Change **Industry → Insurance.** Point at the "1 brand" count and the
"Insurance ✕" chip.
▶ **SAY:** "Filtering re-queries the API. I get a result count and a clearable
filter chip. And when I change a control, focus moves to the results region —
that's for keyboard and screen-reader users so they aren't stranded on the
dropdown." **DO:** Click the ✕ to clear.

**DO:** Tab through with the keyboard; hover a card; click a card.
▶ **SAY:** "Everything's keyboard-operable with native semantic controls. The
whole card is a click target via a stretched link, but it's still a single
semantic heading link underneath. This component passes an axe audit in every
state — loading, empty, error, and success."

**DO (optional, punchy):** Open dev tools → Network, throttle to slow, reload.
▶ **SAY:** "Loading is skeleton cards sized to the real card, so there's no
layout shift. If the request fails you get an error state with retry; zero
results gets a distinct empty state. Those are the three states people forget."

### Beat 2 — The REST API · ~45s
**DO:** Open http://127.0.0.1:8000/api/brands/?sort=avg_rating&dir=desc (DRF browsable API).
▶ **SAY:** "One endpoint returns everything a card needs in a single query —
name, slug, industry, computed average rating, review count, a short
description, and a top-review snippet. No N+1: the list is one aggregate query
plus one prefetch for the top review."

**DO:** Show a few error cases by editing the URL:
- `?industry=nope` → **400** with a `detail` message
- `?sort=bogus` → **400**
- `?page=99` → **404**
▶ **SAY:** "Bad filter or sort is a clean 400 with a message, not a silent
empty 200. Out-of-range page is a 404. That's a real contract a mobile client
could integrate against."

### Beat 3 — The SSR pages · ~30s
**DO:** Open http://127.0.0.1:8000/ then click a brand → `/brand/<slug>/`, then a review → `/review/<slug>/`.
▶ **SAY:** "Server-rendered pages at slugs that match the WordPress permalinks,
so inbound links don't break. Same design tokens as the React app. The body
content is migrated HTML, rendered through an allowlist sanitizer, not a raw
`|safe`."

### Beat 4 — The migration is re-runnable · ~45s
**DO:** In the backend terminal, run `python manage.py import_wordpress` **twice**.
▶ **SAY:** "First run creates 5 industries, 8 reviewers, 5 brands, 60 reviews.
Run it again — everything reports created=0, updated=0. It's fully idempotent.
And if I delete a brand in the DB and re-run, it stays deleted — the migration
never resurrects manually removed rows. I'll explain how in a second."

**DO (optional):** delete a brand via shell, re-run, show it stays gone:
```bash
python manage.py shell -c "from catalog.models import Brand; Brand.objects.first().delete()"
python manage.py import_wordpress   # count stays 4, not back to 5
```

---

## 3. Repo & architecture walkthrough (the guided tour)

▶ **SAY:** "The repo is two apps under `backend/` and a Vite project under
`frontend/`. Let me walk the shape, then the four pillars."

```
backend/
  config/                 # settings, urls, wsgi — project glue
  catalog/                # the domain app (models + SSR + migration)
    models.py             # Industry, Reviewer, Brand, Review, ImportLedger
    querysets.py          # BrandQuerySet.with_stats() — DB-side rating aggregation
    views.py / urls.py    # SSR: home, brand_detail, review_detail
    templates/catalog/    # base, home, brand_detail, review_detail (+ 404)
    templatetags/         # sanitize_html filter (nh3 allowlist)
    management/commands/
      import_wordpress.py # the re-runnable Migration_Command
    wp_import/
      sources.py          # WordPressSource protocol + SqlDumpSource + MariaDbSource
      dump_parser.py      # streaming mysqldump INSERT tokenizer
      importer.py         # idempotent upsert orchestration + ImportLedger logic
  api/
    serializers.py        # BrandCardSerializer + top-review prefetch
    views.py              # BrandListView (DRF ListAPIView)
    pagination.py         # BrandPagination (page-number)
    filters.py            # industry/sort/dir validation → 400s
frontend/
  scss/                   # 7-1 style source tree → static/css/theme.css
  src/
    api/brands.js         # typed fetch wrapper for /api/brands/
    hooks/                # useBrands (state machine) + useUrlSyncedFilters
    components/BrandList/  # BrandList + BrandCard + Filter/Sort controls + states
db/dump.sql               # the WordPress source of truth (committed)
reference/theme.css       # the compiled WP theme we mirror in SCSS
```

▶ **SAY (the mental model):** "Data flows left to right: `db/dump.sql` → a
pluggable source → the idempotent importer → clean relational tables → and from
there two consumers: Django templates for SSR, and DRF for the API that the
React component drives. The seam that makes it all testable is the
`WordPressSource` protocol — the importer never knows *where* the data came
from."

### Guided file tour (open these in order)
1. **`catalog/models.py`** — "Five models. Every imported one carries the WP
   natural key (`wp_post_id`/`wp_user_id`/`wp_term_id`) with a unique
   constraint. That's the idempotency match key *and* the FK-resolution key."
2. **`catalog/querysets.py`** — "`with_stats()` annotates `review_count` and
   `computed_average_rating` in the database with `filter=Q(rating__gte=1)`.
   One definition of 'average', reused by SSR and the API."
3. **`catalog/wp_import/sources.py`** — "The protocol and the two readers. Show
   the postmeta allow-list — that's the whole postmeta strategy in one place."
4. **`catalog/wp_import/importer.py`** — "The upsert flowchart: exists → update;
   in ledger but gone → skip; else create + ledger. This is the heart of the
   're-runnable' requirement."
5. **`api/views.py` + `filters.py` + `serializers.py`** — "Validate params →
   annotate/filter/order in the DB → serialize. Top review is a prefetch."
6. **`frontend/src/hooks/useBrands.js`** — "The `loading|success|empty|error`
   state machine with abortable requests."
7. **`frontend/src/hooks/useUrlSyncedFilters.js`** — "URL is the source of truth."
8. **`frontend/scss/`** — "Tokens → base → layout → components; `@use`, not `@import`."

---

## 4. The six decisions you will defend (scripted answers + rebuttals)

For each: a **headline**, the **why**, and the **rebuttal** to the follow-up
they'll almost certainly ask.

### Decision 1 — Average rating: store, derive, or both?
▶ **HEADLINE:** "Both — but the computed value is authoritative."
▶ **WHY:** "I keep the WordPress ACF `average_rating` on
`Brand.migrated_average_rating` for audit and comparison, but everything the
user sees — SSR and API — comes from a value *computed* from live reviews.
Reviews are the source of truth; a stored aggregate drifts the moment a review
is added or edited. I compute it as a DB annotation so it's still sortable and
cheap."
- **PROBE: "Isn't computing on every request slow?"**
  **ANSWER:** "At this volume it's a single annotated aggregate query, no N+1.
  At 100× I'd add a denormalized `rating_count`/`rating_sum` updated on write
  (signal or a nightly job) and read that — but I wouldn't make that the
  *source of truth*, just a cache. The rule stays 'derive from reviews.'"
- **PROBE: "Why exclude ratings below 1?"**
  **ANSWER:** "The ACF field is 1–5. A 0 means 'no rating captured,' so I treat
  `< 1` as missing data — it's excluded from the mean and the count, and a brand
  with no qualifying reviews reports `null`, not 0. That's Property 1, and it's
  covered by a Hypothesis test."

### Decision 2 — Reviewer modeling
▶ **HEADLINE:** "A dedicated `Reviewer` model — not `auth.User`, not just strings."
▶ **WHY:** "Reviewers are content authors, not people who log in. Coupling them
to Django's auth user would conflate authentication with attribution and drag in
password/permissions machinery I don't want. One `Reviewer` per distinct WP
`post_author` gives a single identity across their reviews. But I *also* keep
the per-review `reviewer_name`/`reviewer_location` ACF strings on the review,
because those are display attributes that can differ from the canonical reviewer
and must survive an unresolved author."
- **PROBE: "What if a review's author doesn't resolve?"**
  **ANSWER:** "The FK is `SET_NULL`-nullable; I import with `reviewer=null` and
  keep the display name. The brand FK, by contrast, is non-null CASCADE — a
  review with no resolvable brand is skipped with a warning, because a review
  without a brand is meaningless."

### Decision 3 — Postmeta strategy (~30 fields per brand)
▶ **HEADLINE:** "First-class columns for the fields I query; retain the two
Yoast keys; drop the rest — including ACF's shadow keys."
▶ **WHY:** "ACF stores each field as a value row plus a shadow `_key` row
pointing at the field definition. I collapse those pairs and keep only the value.
`website_url`, `founded_year`, `headquarters`, `rating`, `reviewer_name`,
`reviewer_location`, and the `brand` reference become typed columns because I
filter/sort/display them. `_yoast_wpseo_title` and `_metadesc` are retained as
SEO fields. Everything else — edit locks, thumbnails, ACF shadow keys — is
dropped."
- **PROBE: "Why not a JSON field for the long tail?"**
  **ANSWER:** "I considered it. For *this* domain the meta set is small and
  known, so typed columns give me validation, indexing, and clean queries. If
  the site had dozens of sparse, unpredictable ACF fields I'd add a single
  `metadata = JSONField` for the long tail and still promote the queryable ones
  to columns. It's a per-field judgment, not all-or-nothing."

### Decision 4 — Migration approach
▶ **HEADLINE:** "A `manage.py` command over a pluggable `WordPressSource`;
SQL-dump by default, MariaDB for scale; idempotent via a ledger."
▶ **WHY (approach):** "I parse the committed `db/dump.sql` by default — it's
always available offline, deterministic, and needs nothing running. But the
importer depends on a `WordPressSource` *protocol*, not the reader, so I can
swap in `MariaDbSource` (streaming server-side cursor) or a REST source without
touching the upsert logic."
▶ **WHY (re-runnable):** "Upsert by the WP natural key. The subtle requirement
is *deletion preservation* — if someone deletes a brand in Django, a re-run must
not bring it back. `update_or_create` would resurrect it. So I keep an
`ImportLedger` of every key I've ever created. The rule per record is: if a live
row exists → update; else if the ledger has seen this key → skip (it was deleted
on purpose); else → create and record it. Each phase runs in
`transaction.atomic()` in FK order: Industries → Reviewers → Brands → Reviews."
- **PROBE: "How does this scale to 100×?"**
  **ANSWER:** "Three things are already in place: the dump parser streams
  line-by-line so memory is flat, `MariaDbSource` uses an unbuffered server-side
  cursor, and FKs resolve via preloaded `{wp_id: pk}` maps instead of per-row
  queries. The one change I'd make is batching writes with `bulk_create`/
  `bulk_update` in chunks — the ledger check is already a set-membership test.
  Beyond that it's a Celery job with checkpointing so a failure resumes."
- **PROBE: "What if the import fails halfway?"**
  **ANSWER:** "Each phase is atomic, so a mid-run failure rolls back that phase
  cleanly — no partial state. An unreadable source raises `CommandError`, exits
  non-zero, and prints no summary, so it's safe to wire into CI/cron."
- **PROBE: "Why not just hit the WP REST API?"**
  **ANSWER:** "It's a valid source and my abstraction supports it, but as the
  *default* it's the weakest: it needs the WP stack up, it's paginated and
  rate-limited, and it's non-deterministic for tests. The dump is the
  reproducible default; REST is the fallback."

### Decision 5 — API contract & component state
▶ **HEADLINE (API):** "DRF page-number pagination, filter by industry *slug*,
an allow-listed sort mapped to DB annotations, clean 400/404s."
▶ **WHY:** "Page-number pagination because both the React control and a future
mobile client think in pages, and `count` lets me render 'N brands' and total
affordances; `next`/`previous` are absolute URLs a client can just follow. I
filter by slug because it's stable and URL-safe and round-trips between the React
URL and the API. Sort is an explicit allow-list (`avg_rating`|`review_count`)
mapped to annotations — so the public contract is decoupled from column names,
and an invalid sort is a clean 400 instead of a silent no-op."
▶ **HEADLINE (state):** "URL query string is the single source of truth; a
`loading|success|empty|error` state machine; abortable fetches."
▶ **WHY:** "Deriving filter/sort from the URL makes state shareable and
back-button friendly for free, and there's exactly one place it lives. The
request lifecycle is an explicit enum, not a tangle of booleans, so every state
has a defined UI. Rapid filter changes abort the in-flight request via
`AbortController` so responses can't race."
- **PROBE: "Why not Redux / React Query / a global store?"**
  **ANSWER:** "For one screen with URL-driven state, that's over-engineering.
  The URL *is* my store. If this grew to many interdependent server-data screens
  I'd reach for React Query for caching/dedup/retries — and my `useBrands` hook
  is already shaped like its API, so that swap is localized."
- **PROBE: "What changes for a mobile client?"**
  **ANSWER:** "Nothing breaking — the same contract serves it. I'd only add
  things: a `fields=` sparse-fieldset param to trim payloads, or cursor
  pagination for infinite scroll. Both additive."

### Decision 6 — SCSS architecture
▶ **HEADLINE:** "A tokens partial mirroring the theme's `:root`, 7-1-style
partitioning, `@use` not `@import`."
▶ **WHY:** "The design values from `reference/theme.css` live once in
`abstracts/_tokens.scss` as SCSS variables re-emitted as CSS custom properties —
so build-time math and runtime theming both work. Then base / layout /
components partials. `@use` gives me namespacing and single-load, so there's no
ordering fragility."
- **PROBE: "How does a second engineer add a component without breaking yours?"**
  **ANSWER:** "They create `components/_thing.scss`, `@use` the tokens, and add
  one line to `main.scss`. Because `@use` is namespaced and non-duplicating, and
  because components don't reach into each other, nothing existing changes.
  That's the whole point of the structure."

---

## 5. Curveball questions (the ones that separate senior from mid)

**Q: Walk me through what happens on `GET /api/brands/?industry=finance&sort=avg_rating&dir=desc`.**
A: "The view validates the three params first — unknown industry slug, sort not
in the allow-list, or bad direction each short-circuit to a 400 with a `detail`
message. Then I build the queryset: `Brand.objects.with_stats()` annotates
`review_count` and `computed_average_rating` in the DB, `select_related`
industry, `prefetch_related` one top review per brand. I filter by the industry
slug, order by the annotation with `nulls_last` regardless of direction, add a
stable `slug` tiebreak for deterministic pagination, then DRF paginates and the
serializer renders the cards. It's one aggregate query + one prefetch query,
independent of page size."

**Q: Where's the N+1 risk and how did you kill it?**
A: "Three places. Industry name → `select_related`. Computed rating/count →
DB annotation, not per-object Python. Top-review snippet → a `Prefetch` that
pulls one ordered top review per brand into `_top_review_cache`, so the
serializer reads memory, not the DB. The model property version of the rating
also reuses the annotation when present so a detail page doesn't re-query."

**Q: How do you know the migration is actually idempotent — not just 'looks like it'?**
A: "It's a formal property, not a vibe. Property 3: importing twice leaves
per-model counts identical *and* every field equal to the first run. It's a
Hypothesis test that generates arbitrary source datasets and runs the importer
twice against an in-memory fake source. Property 5 covers deletion
preservation, Property 4 update propagation, Property 6 reviewer dedup. Plus an
integration test against the real `db/dump.sql`."

**Q: You render migrated HTML with the body. Isn't that stored XSS?**
A: "It would be with a bare `|safe`, which is why I don't. Detail-page bodies go
through a `sanitize_html` template filter backed by nh3 (Rust ammonia) with a
tag/attribute allow-list — `<script>`, event handlers, and `javascript:` URLs
are stripped. Card excerpts are plain-text (`strip_tags` + unescape). It's
defense-in-depth regardless of how the row got into the DB. There are unit tests
asserting scripts and handlers are removed while formatting survives."

**Q: The React app is unauthenticated. Problem?**
A: "It's a public, read-only brand listing, so no — but I'd flag it explicitly.
The moment this API exposed anything mutating or user-specific, it needs
authn/authz, rate limiting, and probably per-user throttling. I called that out
in the README rather than silently shipping an open write surface."

**Q: What's your test strategy, honestly?**
A: "Two layers. Example-based tests pin the concrete contract — API shape,
status codes, SSR fields, 404s. Property-based tests (Hypothesis) prove
universal invariants across generated inputs — the 11 correctness properties:
rating definition, property/annotation agreement, idempotency, update
propagation, deletion preservation, reviewer dedup, slug uniqueness, top-review
rule, pagination invariants, sort monotonicity, filter soundness. Frontend is
Vitest + RTL for the state machine and interactions, plus axe for a11y. 78
backend, 45 frontend."

**Q: What would you *not* have done this way with more time / what's weakest?**
A: "Three honest ones. (1) The computed rating recomputes per request — fine at
5 brands, but at scale I'd cache a denormalized count/sum updated on write. (2)
The importer does row-by-row upserts; the streaming reads are ready but I'd
batch the writes with `bulk_create`/`bulk_update` for the genuine 100× case. (3)
I render sanitized migrated HTML — safer would be to sanitize *on import* and
store clean, so render is trivially safe and the cost is paid once."

**Q: Where did you accept the AI's default over your own preference, and why?**
A: "DRF's default `PageNumberPagination` shape and SQLite for local dev. Both
are appropriate here and trivially swappable — Postgres in prod, cursor
pagination if a mobile client needs infinite scroll. I didn't burn time
customizing things the exercise didn't need. Where I *did* push back on the
default: the naive-datetime bug — the generated importer compared naive vs
timezone-aware `wp_post_date` and marked every row 'updated' on re-run, silently
breaking idempotency. I caught it because Property 3 failed, traced it to the
source layer, and made the parser emit tz-aware UTC. That's the difference
between 'AI wrote code' and 'I own the code.'"

**Q: Why Django templates for SSR instead of Next.js / a SPA everywhere?**
A: "The requirement was permalink-matching server-rendered pages replacing a
WordPress theme. Django templates are the shortest path to that and keep one
framework and one deploy. The interactive piece — the brand listing — is where a
SPA component earns its keep, so that's the one place I used React. Right tool
per surface, not a SPA rewrite of content pages."

**Q: A brand's slug collides / a review points at a missing brand — what happens?**
A: "Slugs are `unique=True` on both models — Property 7 asserts uniqueness holds
across any import. A review whose `brand` reference doesn't resolve can't satisfy
the non-null FK, so it's skipped with a logged warning rather than crashing the
run or inventing a placeholder brand."

**Q: How would you add multi-select industry filtering (likely the live task)?**
A: See section 6.

---

## 6. The live design task (~10–15 min) — how to work it

They'll hand you a new requirement and watch **how you think and how you brief
the AI.** Common ones for this codebase: multi-select industry filter, full-text
search, a "sort by newest review," a favorites/bookmark feature, or a second
API consumer (mobile).

**Your visible method (say it out loud as you go):**
1. **Clarify scope first.** "Before I code — is multi-select an OR within
   industry? Does it need to stay URL-synced and shareable? Any pagination
   interaction?" Interviewers reward this.
2. **State the contract change.** "API: `industry` becomes repeatable —
   `?industry=finance&industry=retail` — validated as 'all must be known
   slugs,' OR semantics, still a 400 if any is unknown."
3. **Name the touch points, end to end.** "`filters.py` validation → `views.py`
   `filter(industry__slug__in=...)` → React `FilterControl` becomes a
   multi-select or checkbox group → `useUrlSyncedFilters` reads/writes repeated
   params → the chip area shows N chips."
4. **Say what protects you.** "Property 11 (filter soundness) already asserts
   every returned row belongs to a requested industry — I'd generalize it to a
   set, and it keeps me honest."
5. **Brief the AI well** (they're watching this): give it the file, the exact
   contract, the constraint ("keep the existing single-value behavior working,
   validate every slug, OR semantics"), and *ask for the test first*. Then read
   the diff critically out loud — "this is mutating the queryset before
   validation, move it after," etc.

**Worked example — multi-select industry (be ready to actually do this):**
- `api/filters.py`: accept `request.query_params.getlist("industry")`; validate
  each against `Industry.objects.filter(slug__in=...)`; 400 if any unknown.
- `api/views.py`: `qs.filter(industry__slug__in=slugs)` when the list is
  non-empty.
- `frontend`: swap `FilterControl`'s single `<select>` for a labelled checkbox
  group (still native, still keyboard-accessible); `useUrlSyncedFilters` uses
  `params.getAll("industry")` / append per value.
- Tests: extend the filter-soundness property to a set membership; add a
  contract test for two industries and for one-unknown-among-known → 400.

**If you get stuck live:** narrate the fallback. "If multi-select validation
gets fiddly, I'd ship single-select correctly and put multi behind a follow-up —
I'd rather ship a correct narrow thing than a broken broad one." That's a senior
answer.

---

## 7. One-paragraph architecture summary (if they ask "sum it up")

▶ **SAY:** "A pluggable `WordPressSource` feeds an idempotent, ledger-backed
importer that upserts WordPress content by natural key into a clean relational
schema. That schema has two consumers: Django templates for permalink-matching
SSR pages, and a DRF endpoint that does all filtering, sorting, and aggregation
in the database and returns everything a card needs in one query. A React
component drives that endpoint with the URL as its single source of truth and an
explicit loading/empty/error state machine, styled by an SCSS token system that
compiles to CSS equivalent to the original theme. Correctness is pinned by 11
property-based invariants plus example and a11y tests."

---

## 8. Cheat sheet (glance during the call)

| Thing | Value |
|---|---|
| Django | http://127.0.0.1:8000 |
| API | http://127.0.0.1:8000/api/brands/ |
| React | http://localhost:5173 |
| Seeded data | 5 industries · 5 brands · 60 reviews · 8 reviewers |
| Tests | backend 78 · frontend 45 · 11 properties |
| Run migration | `python manage.py import_wordpress` |
| Re-run safely | idempotent by WP natural key + `ImportLedger` (skips deleted) |
| Default source | `SqlDumpSource` over `db/dump.sql`; `--source=mariadb` for scale |
| Compile SCSS | `sass frontend/scss/main.scss frontend/static/css/theme.css` |
| Top-review rule | highest `rating>=1`, ties by latest `wp_post_date`, ~160-char excerpt |
| Rating rule | mean of ratings `>=1`; `null` if none; `<1` treated as missing |

**Three sentences that show ownership (drop at least one):**
- "I treat computed rating as authoritative and the ACF value as an audited
  cache, because reviews are the source of truth."
- "The `ImportLedger` exists specifically so a re-run never resurrects a row
  someone deleted on purpose — `update_or_create` can't do that."
- "Property-based testing caught a naive-vs-aware datetime bug that silently
  broke idempotency; that's why the importer emits tz-aware UTC."

---

## 9. Failure recovery during the demo (stay calm)

- **React shows an error state / blank:** the Django server isn't up or CORS/proxy.
  Vite proxies `/api` → :8000; confirm Terminal 1 is running. Reload.
- **API 500 on first hit:** you skipped `import_wordpress` (empty DB) — run it.
- **`import_wordpress` errors:** wrong CWD; run it from `backend/`. Confirm
  `db/dump.sql` exists at repo root.
- **Styles look bare:** the React app imports `static/css/theme.css`; if you
  edited SCSS, recompile with the `sass` command above.
- **A test flakes live:** don't debug on camera — say "let me not rabbit-hole
  here, the suite is green in CI, I'll follow up" and move on.
- **Port already in use:** `runserver 8001` / `npm run dev -- --port 5174` and
  adjust the proxy note; or kill the stale process.
