# Teleprompter Script — WP → Django Migration Walkthrough

Read this top to bottom. Lines in **plain text** are spoken word-for-word at a
natural pace. Lines in `[brackets]` are stage directions — do the action, don't
read it aloud. Pause at each `— (beat) —`.

Total target: ~12 minutes of talking. Breathe between sections.

---

## OPENING — 40 seconds

[Share screen showing the running React app at localhost:5173.]

Thanks for the time. I'm going to walk you through a WordPress-to-Django
migration — the data model, the import, the API, and the React frontend — and
I'll call out the decisions I made and why as I go.

The one-sentence version: WordPress stored everything as denormalized posts and
postmeta. I rebuilt it as a clean relational schema, wrote a re-runnable
importer behind a pluggable source interface, exposed one REST endpoint that
does all the work in the database, and put an accessible, URL-driven React
component on top.

The principle I kept coming back to: reviews are the source of truth, the import
is idempotent, and the API returns everything a card needs in a single query.

[Note: the one-sentence version above isn't one file — it names the four pillars you're about to open. "clean schema" → `backend/catalog/models.py`; "re-runnable importer / pluggable source" → `backend/catalog/wp_import/` (`sources.py` + `importer.py`); "one REST endpoint doing the work in the DB" → `backend/api/views.py` + `backend/catalog/querysets.py`; "URL-driven React" → `frontend/src/components/BrandList/` + `frontend/src/hooks/`.]

— (beat) —

---

## PART 1 — THE PRODUCT, WORKING — 90 seconds

[Point at the page: header, hero, cards.]

This is the React brand listing. I gave it the same page chrome as the migrated
site so it reads as a finished page, not a widget in isolation.

[Change the Sort dropdown to "Highest rated."]

When I sort, watch the URL — it becomes sort equals avg_rating, dir equals desc.
The URL is my single source of truth for filter, sort, and page. So this view is
shareable, bookmarkable, and the back button just works.

[Change Industry to "Insurance."]

Filtering re-queries the API. I get a live result count, and a clearable filter
chip. And notice the sorting happened in the database, not in JavaScript — so
it's correct across the whole result set, not just the page I'm looking at.

[Tab with the keyboard to show focus rings; then clear the chip.]
[Backing code if they ask mid-demo: sorting is server-side in `backend/api/views.py`; the count/chip + focus-move are in `frontend/src/components/BrandList/BrandList.jsx` (`brand-list__count`, `filter-chip`, `resultsRef`/`pendingFocusRef`); star-rating text is in `BrandCard.jsx`.]

Everything is keyboard-operable with native controls, the star ratings expose a
text value to screen readers, and after any change I move focus to the results
region so a screen-reader user lands on the new content instead of being
stranded on the dropdown.

— (beat) —

That's the surface. Let me show you what's underneath.

---

## PART 2 — THE DATA MODEL — 2 minutes

[Open `backend/catalog/models.py` — the 5 model classes: Industry, Reviewer, Brand, Review, ImportLedger.]

First decision: the schema. WordPress gives you two post types — brand and
review — plus an industry taxonomy, all crammed into posts and postmeta. I did
not preserve that shape. I modeled the domain: Industry, Brand, Review, and a
dedicated Reviewer.

[Point at the foreign keys in models.py — `Brand.industry` on_delete=PROTECT (~line 76); `Review.brand` on_delete=CASCADE (~line 135); `Review.reviewer` on_delete=SET_NULL (~line 143).]

The relationships carry intent. A Brand's industry is PROTECT and non-null — you
can't orphan a brand. A Review's brand is CASCADE — reviews die with their
brand. A Review's reviewer is SET_NULL and nullable — attribution can be
unknown, and I don't want to lose a review because I couldn't resolve its
author.

— (beat) —

Second decision, and this is one I expect you to push on: the average rating.

[Point at `migrated_average_rating` in models.py (~line 65), then open `backend/catalog/querysets.py` — `BrandQuerySet.with_stats()` (~line 19), the `computed_average_rating=Avg(...)` line (~line 32).]

WordPress had an average_rating field on the brand. A brand also has individual
reviews with their own ratings. So do I store the average, derive it, or both?

I do both — but with a clear authority rule. I keep the WordPress value on
migrated_average_rating purely for audit, so I can compare what WordPress
claimed against reality. But the value the user and the API actually see is
computed from live reviews, right here in with_stats — a database annotation
that averages the ratings of one or greater.

The reason is simple: reviews are the source of truth. A stored aggregate drifts
the moment a review is added or edited. Computing it keeps the number honest, and
doing it as an annotation keeps it cheap and sortable in the database.

[Back in models.py, point at the `computed_average_rating` @property + setter on Brand (~lines 100–125). The test that proves agreement: `backend/catalog/tests/test_rating_properties.py`.]

There's a matching property on the model for single-object use, so a detail page
never triggers an N-plus-one — and I have a property-based test that proves the
property and the annotation always agree.

— (beat) —

[Point at `class Reviewer` in models.py (~line 35), then the `reviewer_name` / `reviewer_location` fields on `class Review`.]

On reviewers: I used a dedicated Reviewer model, not Django's auth user. These
are content authors, not people who log in — coupling them to authentication
would be conflating two different things. One Reviewer per WordPress author gives
a single identity across reviews, and I still keep the per-review display name on
the review itself, so it survives even when the author can't be resolved.

---

## PART 3 — THE IMPORT — 2.5 minutes

[Open `backend/catalog/wp_import/sources.py` — the `WordPressSource` Protocol near the top, then `class SqlDumpSource` and `class MariaDbSource`. (The streaming tokenizer it uses is `dump_parser.py`.)]

The migration. The most important decision here is that the importer depends on
an interface — WordPressSource — not on a concrete reader.

[`class SqlDumpSource` and `class MariaDbSource` are both in sources.py; the four dataclasses (SourceIndustry/User/Brand/Review) are near the top.]

The default is SqlDumpSource, which parses the committed SQL dump. It's offline,
deterministic, and doesn't need the WordPress stack running — which makes it
great for CI. There's also MariaDbSource, the same four methods backed by a live
database with a server-side cursor, for scale. Both yield plain dataclasses, so
the upsert logic never knows or cares where the data came from.

[Open `backend/catalog/wp_import/importer.py`; `run_import` is at the bottom (~line 416), the phases above it.]

Now the re-runnable requirement — this is the subtle part. Re-running has to be
idempotent, and it must never resurrect a row someone deleted on purpose.

[Scroll to `_upsert_industries` (~line 116) — it's the shortest phase. The three branches are right there: update → `to_update.append(live)` (~138); SKIP → `elif wp_id in ledger_keys:` (~139) ← say the "deleted on purpose" line with the cursor HERE; create → `to_create.append(...)` + `_record_in_ledger(...)` (~142–148).]

For each record I do a three-way branch. If a live row exists, I update the
changed fields. If it doesn't exist but the ledger has seen its key before, I
skip it — because it was imported once and then deleted, and I have to respect
that deletion. Only if it's genuinely new do I create it and record it in the
ledger.

That ledger is the whole trick. A plain get-or-create or update-or-create would
happily bring a deleted row back to life on the next run. The ImportLedger is
what lets me tell "never seen" apart from "deleted on purpose."

[The ledger table is `class ImportLedger` in models.py (~line 173); `_load_ledger_keys` is at the top of importer.py (~line 86). The explicit test for this branch: `backend/catalog/tests/test_importer_ledger.py`.]

— (beat) —

[Point at the tail of `_upsert_industries` — `bulk_create` (~147) / `bulk_update` (~150). The FK id-maps are built in `run_import` (~lines 430–445, `industry_map` / `reviewer_map` / `brand_map`); each phase runs in `transaction.atomic()` there.]

For scale: each phase classifies its rows into create, update, or skip, and then
writes them with chunked bulk_create and bulk_update — so a phase costs a bounded
number of statements, not one per row. Foreign keys resolve through preloaded
id-maps, not per-row lookups. Each phase is wrapped in an atomic transaction, so
a mid-run failure rolls back cleanly.

[Switch to the terminal. Run: `python manage.py import_wordpress` (or `make seed`). Command lives at `backend/catalog/management/commands/import_wordpress.py`.]

Here it is against the real dump — five industries, eight reviewers, five brands,
sixty reviews.

[Run it again immediately.]

And the second run: everything zero. Fully idempotent — no creates, no updates.

— (beat) —

One thing I'll own here: I caught a real bug with this. My first version marked
every row as "updated" on re-run. The cause was that WordPress timestamps are
naive, but Django reads them back as timezone-aware, so my change-detection
always saw a difference. A property test — "a re-run changes nothing" — is what
surfaced it. I fixed it by making the parser emit timezone-aware UTC. That's the
difference between AI writing code and me owning it.

[If asked to show the fix: `_make_aware_utc()` in `sources.py`, used by `_to_datetime`. The idempotency property is `test_property_import_idempotency` in `backend/catalog/tests/test_importer_properties.py`.]

---

## PART 4 — THE API — 2 minutes

[Open `backend/api/views.py` — `class BrandListView` and its `get_queryset()`.]

One endpoint: GET slash api slash brands. It's a DRF list view over that
annotated queryset.

[The `validate_industry` / `validate_sort` / `validate_direction` calls are the first lines of `get_queryset`; their logic (and the sort allowlist) lives in `backend/api/filters.py`. The `order_by(... nulls_last=True ..., "slug")` is at the end of `get_queryset`.]

I validate the parameters before I touch the database — an unknown industry, a
bad sort key, or a bad direction each return a clean 400 with a message, not a
silent empty 200. I filter by industry slug, because a slug is stable and
URL-safe and round-trips between the React URL and the API. Sorting is an
explicit allowlist mapped onto the database annotations, with nulls ordered last
regardless of direction, and a stable slug tiebreak so pagination doesn't shuffle
between pages.

[Open `backend/api/serializers.py` — `top_review_prefetch()` (the correlated `pk__in=Subquery(... OuterRef("brand") ...[:1])`) and `BrandCardSerializer`. Pagination cap lives in `backend/api/pagination.py`.]

Each card needs a "top review" snippet. The rule is documented right here:
highest rating, ties broken by most recent date. And I load exactly one review
per brand — this prefetch uses a correlated subquery so it pulls one row per
brand in a single query, instead of pulling every review and throwing all but one
away. So the whole list is a small, constant number of queries no matter how many
brands or reviews there are.

[Switch to browser, hit /api/brands/?industry=nope — show 400. Then ?page=99 — show 404.]

Bad filter, clean 400. Page out of range, 404. That's a contract a mobile client
could integrate against tomorrow.

— (beat) —

There's also a small industries endpoint — that exists so the filter dropdown
can load the full set of industries independently, instead of only knowing about
industries it happens to have seen in the current results.

[`IndustryListView` in `views.py`, wired at `/api/industries/` in `backend/api/urls.py`. The cached slug validation is `get_industry_slugs()` in `backend/catalog/cache.py`, invalidated by signals in `catalog/apps.py`.]

---

## PART 5 — THE FRONTEND — 2 minutes

[Open `frontend/src/hooks/useUrlSyncedFilters.js` — `setFilters` and its `changesFilter && !("page" in patch)` reset rule.]

On the frontend, state is split cleanly. This hook owns filter, sort, direction,
and page — all in the URL. The URL is the source of truth. And there's one subtle
rule here: changing a filter or sort resets the page to one, because the old page
number is meaningless against a different result set.

[Open `frontend/src/hooks/useBrands.js` — the `BrandsStatus` enum + the effect with `AbortController`. (The typed fetch wrapper is `frontend/src/api/brands.js`.)]

This hook owns the request lifecycle as an explicit state machine — loading,
success, empty, error — not a tangle of booleans. It fetches on mount, re-fetches
when the params change, and aborts in-flight requests, so if I change filters
quickly the old responses can't race the new one.

[Open `frontend/src/components/BrandList/BrandList.jsx` — the status switch in the JSX (`Loading`/`Empty`/`Error` from `states.jsx`), and the `Pagination` sub-component + `pageWindow()` helper at the bottom of the file.]

The component itself is thin — it wires the hooks to presentational pieces. Every
state has a real UI: skeleton cards on load so there's no layout shift, a proper
empty state, and an error state with retry. The pagination is windowed — first,
last, and a couple around the current page with ellipses — so the control stays
compact even at a thousand pages.

[Open `frontend/scss/abstracts/_tokens.scss` — the SCSS vars → `:root` custom properties, and the `@media (prefers-color-scheme: dark)` override block at the bottom. Entry point is `frontend/scss/main.scss`.]

And the styling is a token system. The design values live once, here, as
variables re-emitted as CSS custom properties — so I get build-time use and
runtime theming. Because everything reads those tokens, dark mode is a single
override block at the bottom; no component partial changes. Adding a new
component is a new partial plus one line — it never touches existing files.

— (beat) —

---

## PART 6 — TESTING — 45 seconds

[Optional: switch to terminal, show test counts, or just speak.]

On testing — two layers. Example tests pin the concrete contract: API shapes,
status codes, the rendered pages. And property-based tests, with Hypothesis,
prove the invariants across generated inputs — the average-rating definition,
import idempotency, deletion preservation, sort monotonicity, pagination
integrity. Eighty-something backend tests, sixty-something frontend, plus axe for
accessibility and a stylelint rule that structurally prevents CSS selector
collisions.

The property tests are the ones I'm proudest of, because they test the cases I
didn't think of — that's how I found the timezone bug.

---

## CLOSE — 20 seconds

So that's the shape of it: model the domain honestly, make the boundaries
pluggable, keep the invariants executable, and let the URL and the database do
the work instead of piling state into the client.

I'm happy to go deeper on any layer, or take a new requirement and design it with
you.

— (beat, then stop talking and let them drive) —

---

## EMERGENCY ONE-LINERS (if you blank)

- **Average rating:** "Reviews are the source of truth; a stored average drifts."
- **The ledger:** "It tells 'never imported' from 'deleted on purpose,' so a
  re-run never resurrects a deletion."
- **Source interface:** "The importer never knows where the data came from —
  that's the scaling seam."
- **URL as state:** "Shareable, back-button friendly, and I don't need a state
  library."
- **Slug filtering:** "Stable and URL-safe, so it round-trips between the React
  URL and the API."
- **Top review:** "One row per brand via a correlated subquery — no N-plus-one."

---

## IF THE DEMO BREAKS (say this, stay calm)

"Let me not rabbit-hole on the environment — the suite is green in CI. Let me
walk you through the code instead and I'll circle back." [Then switch to the
editor and keep going from the relevant PART above.]
