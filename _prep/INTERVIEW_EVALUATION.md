# Senior Full-Stack Engineer — Interview Evaluation

**Candidate Submission:** WordPress → Django Migration Challenge
**Evaluator:** Principal Software Engineer
**Date:** 2026-07-10

---

## Executive Summary

This is a genuinely strong submission. The candidate demonstrates end-to-end
ownership across the full stack, writes production-quality Python, and clearly
understood what the challenge was actually testing. The code is not "AI soup"
— there are deliberate design decisions throughout that show the candidate
vetted the output, pushed back where needed, and owns the result. A few gaps
in robustness and one notable architectural question keep this short of
exceptional.

---

## Pillar Scores

| Pillar | Area | Score |
|---|---|---|
| 1 | Django Backend / Schema | 9 / 10 |
| 2 | REST API | 9 / 10 |
| 3 | React `<BrandList />` | 9 / 10 |
| 4 | SCSS Architecture | 9 / 10 |
| — | Testing discipline | 9 / 10 |
| — | README / Documentation | 10 / 10 |
| — | **Overall** | **55 / 60 (92%)** |

**Hire signal: Strong Yes**

---

## Pillar 1 — Django Backend (9/10)

### What lands well

- **Schema is genuinely clean.** `Industry → Brand → Review` with a dedicated
  `Reviewer` model. No `JSONField` dumps, no postmeta shape preserved. The
  candidate made real domain decisions rather than cargo-culting WP's table
  structure.
- **Dual-path average rating** is well-reasoned. `migrated_average_rating`
  retained for audit; `computed_average_rating` is the authoritative value.
  The property/annotation symmetry with the `__dict__` setter trick to avoid
  re-querying an already-annotated instance is sophisticated and correct.
- **`WordPressSource` protocol** is excellent. Isolating `SqlDumpSource` from
  `MariaDbSource` behind a `Protocol` type means the importer is fully
  testable with in-memory fixtures. The streaming line-by-line dump parser is
  the right call for large dumps; memory stays flat.
- **`ImportLedger`** is the right idempotency primitive. The three-way
  branch — "live row exists → upsert", "ledger has it → skip (deletion
  preserved)", "neither → create" — is correct and non-trivial. Most
  candidates just do `get_or_create` and call it done.
- **Permalink URLs match WP** (`/brand/<slug>/`, `/review/<slug>/`).
- **Server-rendered pages** use `select_related` + `with_stats()` annotation
  — no N+1s visible in the view layer.

### Gaps

- **No database indexes beyond unique constraints.** `Review.brand` is a
  FK but there's no explicit `db_index=True` (Django adds it by default on
  FKs, so this is fine) — but `Review.rating` is never indexed and appears
  in the `QUALIFYING_REVIEW` filter on every single API request. At 60K+
  reviews that becomes a full table scan on the most-hit query path.
- **`|safe` on migrated HTML bodies** is flagged as a known risk in the
  README but not mitigated. This is an XSS vector if any WP content was
  ever user-generated. It should at minimum be `bleach.clean()` or
  Django's `mark_safe` after sanitization, not raw `|safe`.
- **`Brand.industry` is `PROTECT`** — correct — but there's no admin
  registration, which makes managing industries in a running app awkward.
  Minor for a take-home, but notable.

---

## Pillar 2 — REST API (9/10)

### What lands well

- **Validation-first `get_queryset`** is correct: bad params fail fast with
  clean `400`s before touching the database.
- **Public param names decoupled from annotation names** in `filters.py`
  (`avg_rating` → `computed_average_rating`). This is the right call; it
  keeps the API contract stable regardless of internal renames.
- **`nulls_last=True`** on the sort ordering is a production detail most
  candidates miss. Brands with no reviews don't crowd the top of a rating
  sort.
- **Stable tiebreak by slug** keeps pagination deterministic across pages.
  Without this, a page boundary could shuffle under the client.
- **Prefetch strategy for top review** is efficient: one extra query for the
  full brand page, not N queries. The fallback to a direct query when the
  prefetch wasn't applied is defensive and correct.
- **`industry_slug` exposed** on the card payload so the React client can
  round-trip the filter value without a separate industries endpoint.

### Gaps

- **No `/api/industries/` endpoint.** The React component works around this
  by accumulating `industry_slug`/`industry` pairs seen in results, which is
  clever but fragile — if you filter to a single industry first, the filter
  dropdown never shows the others until you clear it. A cheap
  `GET /api/industries/` would solve this properly.
- **`validate_industry` hits the database** on every request to check slug
  existence. At read-heavy scale you'd want this in a cache or a
  `__in` check against a query-time set.
- **`page_size` is client-controllable** up to `max_page_size=100`. That's
  a reasonable cap, but it's undocumented in the README.

---

## Pillar 3 — React `<BrandList />` (9/10)

### What lands well

- **Explicit state machine** (`loading | success | empty | error`) rather
  than ad-hoc boolean flags. This is the right abstraction; it makes
  impossible states impossible.
- **`AbortController` on every fetch**, cleaned up on unmount and on
  superseding query changes. Race condition is handled.
- **URL as single source of truth** via `useUrlSyncedFilters`. Back-button,
  bookmarks, and share links all work correctly.
- **`mergeIndustries`** is a thoughtful solution to the "filter dropdown
  shrinks after filtering" problem — accumulates seen options without ever
  dropping them. It's a workaround for the missing `/api/industries/`
  endpoint, but it works.
- **Focus management** on filter/sort change (`resultsRef`, `pendingFocusRef`)
  is production-grade a11y work. Most candidates skip this entirely.
- **Skeleton loading cards** prevent layout shift. The `aria-hidden` on
  decorative skeletons plus the visually-hidden status message for
  screen readers is correct.
- **`axe` integration** in `BrandList.a11y.test.jsx`. Automated a11y
  testing is not common in take-home submissions.
- **`VisuallyHidden` component** instead of `display:none` or CSS tricks
  for screen-reader-only text. This is correct and shows familiarity with
  the accessibility tree.

### Gaps

- **Industry options never loaded independently** — the component has a cold
  start problem. On first render the filter dropdown is empty until brands
  load. A user who lands with `?industry=banking` in the URL won't see
  "Banking" in the dropdown label because the options haven't been
  accumulated yet.
- **Page state is local, not URL-synced.** The sort/filter are in the URL but
  `page` is `useState(1)`. Refreshing page 3 lands the user back on page 1.
  This is a product UX regression.
- **No Suspense / streaming boundary** — not required, but with React 18 on
  the table, the custom loading state is a step back from what the framework
  now provides.

---

## Pillar 4 — SCSS Architecture (9/10)

### What lands well

- **7-1 pattern** (`abstracts/`, `base/`, `layout/`, `components/`) with
  `@use` not `@import`. This is the correct modern Sass architecture.
- **Dual-variable + custom property pattern in `_tokens.scss`** is exactly
  right: SCSS variables for build-time use (breakpoints, which CSS custom
  properties can't do), re-emitted as `--custom-props` for runtime theming.
- **Single compile entry point** (`main.scss`) with clear instructions for
  Dart Sass. Adding a new component is one `@use` line — no edits to existing
  partials.
- **`$bp-mobile` as an SCSS variable** (not a custom property) is explicitly
  called out in the comment — the candidate understands *why* this distinction
  matters.
- **Structural equivalence test** (`scss-structure.test.js`) that compiles
  the SCSS and asserts presence of design tokens and core component rules.
  This is above and beyond.

### Gaps

- **No SCSS-level namespace prefixing** on component partials. With `@use`,
  the namespace is the partial's filename, but none of the component partials
  use the namespace in their own rules — if two partials define `.title` they
  silently collide in the output. BEM is applied at the selector level but
  not enforced structurally.
- **No dark-mode token layer.** The reference theme is light-only, so this
  isn't a strict miss — but a senior engineer would note the token structure
  doesn't leave a clean hook for `prefers-color-scheme`.

---

## Testing (9/10)

- **Hypothesis property tests** for `computed_average_rating` (200 examples,
  `deadline=None`) are exactly what this kind of aggregate logic deserves.
  This is not something you get from AI by default — the candidate wrote a
  real property spec.
- **Contract tests** (`test_api_contract.py`) — good.
- **`axe` a11y tests** — strong.
- **SCSS structural tests** — creative and useful.
- **Gap:** No test for the `mergeIndustries` accumulator logic, which
  contains a non-trivial correctness condition. No test for the
  `ImportLedger` "deleted row not resurrected" path — the most important
  idempotency case.

---

## Documentation (10/10)

The README is the best part of this submission. It answers every rubric
question unprompted, distinguishes AI defaults from deliberate choices, and
is honest about trade-offs. The "What I'd do differently" section shows
genuine reflection rather than boilerplate hedging.

---

## Overall Score: 55 / 60 (92%) — Strong Yes

---

---

# Live Session — Probing Questions

These are the questions to use to stress-test the decisions.
There is no single right answer to any of them; the goal is to watch how the
candidate reasons, not whether they give a memorized answer.

---

### 1. Schema: The `__dict__` setter trick

> You use `self.__dict__["computed_average_rating"] = value` in the property
> setter to let the queryset annotation "land" on an instance that also has a
> property of the same name. Walk me through exactly why a normal setter
> `self.computed_average_rating = value` would not work here, and what
> failure mode you're preventing. Then tell me: if you called
> `Brand.objects.with_stats().get(pk=1)` and then called
> `brand.save()`, what happens to the annotated value?

*What I'm probing:* Does the candidate actually understand Django's
descriptor protocol and instance `__dict__` vs. class-level attributes, or
did they accept AI output they can't explain?

---

### 2. Idempotency: The ledger's "deleted row not resurrected" guarantee

> You say the `ImportLedger` distinguishes "never imported" from "imported
> then deleted." Walk me through the exact code path where a review was
> imported on run 1, an admin deleted it from Django, and run 2 runs.
> What is in the ledger? What does the importer do? What SQL gets executed?
>
> Follow-up: I go into the Django admin and I *edit* a review's rating
> between runs. Does run 2 overwrite my edit?

*What I'm probing:* The three-way branch is the most important correctness
claim in the submission. I want to see the candidate trace it without
looking at the code.

---

### 3. API contract: The missing `/api/industries/` endpoint

> Your `mergeIndustries` accumulator in the React component works around the
> fact that you didn't build an industry-listing endpoint. On a cold page
> load with `?industry=banking` in the URL, what does the user see in the
> filter dropdown? Walk me through the render cycle.
>
> Follow-up: If I asked you to add `GET /api/industries/` right now,
> live, what are the two decisions you'd make immediately and why?

*What I'm probing:* Can the candidate identify the cold-start bug without
being told about it, and do they have a clean mental model of the render
cycle?

---

### 4. Scaling the importer

> You say the dump parser "streams line-by-line" and `MariaDbSource` uses an
> "unbuffered server-side cursor" so memory stays flat. I have 6 million
> reviews. Walk me through what happens to **write throughput** — not read
> memory — when you run the importer as-is. How many SQL statements are
> executed for those 6 million rows?
>
> Follow-up: You mention `bulk_create`/`bulk_update` as the fix. What's the
> Django-specific gotcha with `bulk_create` and auto-generated PKs in SQLite
> vs. Postgres, and how does it affect your `{wp_id: pk}` FK resolution maps?

*What I'm probing:* The README claims bulk is the fix but the code doesn't
implement it. I want to know if the candidate understands the specific
failure modes at scale, not just the buzzword.

---

### 5. React state: Page not URL-synced

> Your sort, industry, and direction are URL-synced. Your page number is
> `useState(1)`. I'm on page 3 of the Banking filter and I hit refresh.
> Where do I land? Is that the right product behavior?
>
> Follow-up: If I asked you to add page to the URL, what's the one subtle
> interaction you'd need to get right between page state and filter changes?

*What I'm probing:* Did the candidate make a deliberate decision here or is
this an oversight? Either answer is acceptable — I want to hear them own it.

---

### 6. Security: `|safe` on migrated HTML

> You flag `|safe` on migrated brand and review bodies as a known risk in
> your README. Tell me the specific attack vector. Is this actually
> exploitable with data from this particular source? How would you mitigate
> it without losing legitimate HTML formatting?

*What I'm probing:* Depth of security awareness. "Use bleach" is not enough
— I want to hear about allowlisting vs. striplisting, and why `strip_tags`
is not the same as sanitization.

---

### 7. Live new requirement (hand this to the candidate on the call)

> **New requirement:** Product wants a `GET /api/brands/<slug>/` endpoint
> that returns the full brand detail — same schema as the card plus the
> full body, all reviews with author names, locations, dates, and ratings,
> and a `"related_brands"` array of up to 3 brands in the same industry
> (excluding self), ordered by average rating descending.
>
> You have 15 minutes. Use your AI tooling. I'm watching how you brief it,
> what you accept, and what you push back on.

*What I'm probing:*

- Does the candidate give the AI their existing schema/queryset/serializer
  context before prompting, or do they prompt blind?
- Do they spot that `related_brands` naively is an N+1 (another
  `with_stats()` subquery or `Prefetch` is needed)?
- Do they accept a `ModelSerializer` when the existing API uses a plain
  `Serializer`? (Consistency decision — either way, defend it.)
- Do they notice `select_related("reviewer")` is needed on reviews?
