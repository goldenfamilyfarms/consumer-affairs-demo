# Walkthrough: `frontend/src/` — the React `<BrandList />`

This is the interactive brand listing that consumes `GET /api/brands/`. The
whole thing is built around one idea: **the URL is the source of truth, and the
component is thin.** State lives in the query string, data-fetching lives in a
hook with an explicit state machine, and the pieces that draw things are dumb
presentational components.

Here's the layout:

```
src/
  api/
    brands.js            → typed fetch wrapper for /api/brands/
    industries.js        → fetch wrapper for /api/industries/
  hooks/
    useUrlSyncedFilters.js → filter/sort/dir/page ↔ the URL query string
    useBrands.js           → the loading|success|empty|error request machine
    useIndustries.js       → loads the full industry list for the dropdown
  components/BrandList/
    BrandList.jsx          → the container that wires it all together
    BrandCard.jsx          → one brand card
    FilterControl.jsx      → the industry <select>
    SortControl.jsx        → the combined sort <select>
    states.jsx             → Loading / Empty / Error views
    VisuallyHidden.jsx     → screen-reader-only text helper
  App.jsx                  → page chrome (header, hero, footer) + <BrandList/>
  main.jsx                 → React entry point, imports the compiled theme CSS
```

Let me go layer by layer, bottom up.

---

## `api/brands.js` and `api/industries.js` — the fetch wrappers

These are thin, typed wrappers around `fetch`. `brands.js` exports
`fetchBrands(query, options)` which builds the query string from a typed object
(`industry`, `sort`, `dir`, `page`, `pageSize` → `page_size`), calls the
endpoint, and:

- throws a custom `BrandApiError` (carrying the HTTP status and the API's
  `{detail}` message) on a non-2xx response, and
- accepts an injected `fetchFn` and an `AbortSignal` — the injectable fetch makes
  it trivial to test, and the signal is what lets us cancel in-flight requests.

`industries.js` is the same idea for the unpaginated `/api/industries/` list.

Keeping these separate from React means the "how do I talk to the API" knowledge
lives in one place, and the hooks/components never touch `fetch` directly.

---

## `hooks/useUrlSyncedFilters.js` — the URL *is* the state

This hook is the heart of the state design. Instead of holding filter/sort/page
in component state, it reads and writes them to the browser's query string:

- `readFiltersFromSearch(search)` parses `industry`, `sort`, `dir`, and `page`
  out of the URL (page normalizes to 1 if missing or junk).
- `setFilters(patch)` merges a change, writes it back with the History API
  (`pushState`), and updates state so the component re-renders.
- It listens for `popstate`, so the browser back/forward buttons just work.

The one subtle rule that's easy to get wrong: **changing a filter or sort resets
the page to 1.** The old page number is meaningless against a different result
set. You can see it in `setFilters` — if the patch changes a filter/sort key and
doesn't explicitly set a page, page snaps back to 1. (Also, `page=1` is left out
of the URL to keep it clean.)

Why do it this way instead of Redux/Zustand? For one screen whose state is
naturally URL-shaped, the URL *is* the store — and you get shareable links,
bookmarks, and back-button support for free.

> Interview one-liner: *"Filter/sort/page live in the URL, so the view is
> shareable and back-button friendly with no state library — and changing a
> filter resets the page, because the old page is meaningless against new
> results."*

---

## `hooks/useBrands.js` — an explicit request state machine

This hook owns the request lifecycle as a named enum — `BrandsStatus` =
`loading | success | empty | error` — instead of a tangle of boolean flags. That
makes impossible states impossible (you can't be "loading and error" at once).

What it does:

- Fetches on mount, and **re-fetches whenever the query params change**
  (it keys the effect off a stable serialization of the query, so passing a
  fresh object literal each render doesn't cause spurious refetches).
- Uses an `AbortController` per request — so if you change filters quickly, the
  previous request is cancelled and can't "win" a race and overwrite newer
  results. An aborted request is ignored, not treated as an error.
- Distinguishes **empty** (a successful response with zero rows) from **success**
  (one or more rows), because those are different UIs.
- Exposes a `retry()` for the error state.

> Interview one-liner: *"An explicit loading/success/empty/error machine with
> abortable fetches — rapid filter changes cancel the old request instead of
> racing it."*

---

## `hooks/useIndustries.js` — the filter's data source

Small hook that fetches the full industry list once on mount and returns
`{ industries, failed }`. It's deliberately **non-critical**: if the endpoint is
down it doesn't blow up — it returns `failed: true` and an empty list, and the
component falls back to whatever industries it can derive from the brand results,
while showing a subtle "options will appear as brands load" hint. So a flaky
industries endpoint degrades gracefully instead of leaving an empty dropdown.

---

## `components/BrandList/BrandList.jsx` — the container

This is where everything gets wired, and it stays thin:

- Pulls `filters` + `setFilters` from `useUrlSyncedFilters`, builds the query,
  and passes it to `useBrands`.
- Builds the dropdown options by unioning the industries from `useIndustries`
  with any seen in the current results (`mergeSeenIndustries`) — so the list is
  complete even on a cold `?industry=…` load, with the result-derived set as a
  fallback.
- Renders the toolbar (filter + sort controls, a live result count, and a
  clearable "active filter" chip).
- Switches on the status enum to render `Loading` / `Empty` / `Error` / the grid
  of `BrandCard`s.
- **Focus management (accessibility):** after a *user-initiated* change lands
  (not on first mount), it moves keyboard focus to the results region so a
  screen-reader user is taken to the new content instead of being stranded on
  the dropdown. There's a `pendingFocusRef` flag that gets set on interaction and
  consumed once results settle.

At the bottom of the file lives the `Pagination` component and its `pageWindow`
helper. `pageWindow` builds a compact list of page buttons — always first + last,
the current page ±1, and `"ellipsis"` markers for the gaps — so even with 1,000
pages the control stays ~7 items instead of rendering a thousand buttons.

> Interview one-liner: *"The container is thin — it wires hooks to presentational
> pieces, unions the dropdown options so the filter's always complete, and moves
> focus to the results after a change for a11y."*

---

## The presentational pieces

- **`BrandCard.jsx`** — a semantic `<article>` with a heading that links to the
  brand detail page. The star rating is accessible: the glyphs are decorative
  (`aria-hidden`) and the real value is exposed as text ("Average rating 4.2 out
  of 5") for screen readers. Zero-review brands show "No ratings yet." The whole
  card is clickable via a stretched link, but it's still one semantic heading
  link underneath.
- **`FilterControl.jsx`** — a native, labelled `<select>` for the industry. Native
  because it's keyboard-accessible and screen-reader-correct for free.
- **`SortControl.jsx`** — one combined `<select>` where each option is an *intent*
  ("Highest rated", "Most reviewed") rather than making the user pick a key and a
  separate direction. Each option maps to a `{sort, dir}` pair.
- **`states.jsx`** — the `Loading` (skeleton cards so there's no layout shift,
  plus a visually-hidden "Loading brands…" for screen readers), `Empty`, and
  `Error` (with a Retry button) views. They render inside `aria-live` regions so
  transitions get announced.
- **`VisuallyHidden.jsx`** — a tiny helper that hides content visually but keeps
  it in the accessibility tree (the correct way to do screen-reader-only text,
  vs `display:none` which hides it from everyone).

---

## `App.jsx` and `main.jsx`

- **`App.jsx`** gives the app the same chrome as the server-rendered site — a
  header with nav, a hero, a footer — so it reads as a finished page, not a
  floating widget, and then mounts `<BrandList />`.
- **`main.jsx`** is the React entry point; it also imports the compiled
  `theme.css` so the React app is styled by the same design tokens as the SSR
  pages.

---

## Testing (alongside these files)

- `hooks/useUrlSyncedFilters.test.js` — the parse/build/reset-page logic and
  popstate resync.
- `hooks/useBrands.test.js` — the state-machine transitions and abort behavior.
- `components/BrandList/BrandList.test.jsx` — loading→success→N cards, empty,
  error+retry, filter/sort trigger refetch + update the URL, init-from-URL.
- `BrandList.a11y.test.jsx` — labelled/keyboard-operable controls, star text
  value, and an `axe` audit of each state.
- `BrandList.polish.test.jsx`, `pageWindow.test.js`, `mergeSeenIndustries.test.js`,
  `BrandList.industries.test.jsx`, `BrandList.pagination.test.jsx` — the result
  count, the windowed pager, the option accumulator, the industries cold-start,
  and the URL-synced page.

---

## TL;DR

- **URL = state** (`useUrlSyncedFilters`) → shareable, back-button friendly.
- **`useBrands`** = an explicit loading/success/empty/error machine with
  abortable fetches.
- **`BrandList`** is a thin container; the cards/controls/states are dumb and
  accessible; pagination is windowed.
- The whole thing is keyboard-operable, `axe`-clean, and styled by the shared
  design tokens.

One sentence: **push state into the URL, model the request as a state machine,
and keep the component a thin wiring layer over accessible presentational parts.**
