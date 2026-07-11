/**
 * BrandList — interactive, accessible brand listing (Requirement 12).
 *
 * Responsibilities:
 *   - Derive industry/sort/direction/page from the URL via `useUrlSyncedFilters`
 *     (Req 12.8) — the single source of truth, including the page number.
 *   - Fetch brand data through `useBrands` (fetch on mount, re-fetch on param
 *     change, abortable) and render loading / success / empty / error.
 *   - Populate the industry filter from `useIndustries` (a dedicated endpoint)
 *     so the dropdown is complete even on a cold `?industry=…` load, falling
 *     back to industries seen in the results if that endpoint is unavailable.
 *   - Move focus to the results region after a user-initiated change (a11y).
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { useBrands, BrandsStatus } from "../../hooks/useBrands.js";
import { useUrlSyncedFilters } from "../../hooks/useUrlSyncedFilters.js";
import { useIndustries } from "../../hooks/useIndustries.js";
import BrandCard from "./BrandCard.jsx";
import FilterControl from "./FilterControl.jsx";
import SortControl from "./SortControl.jsx";
import { Loading, Empty, Error } from "./states.jsx";

/** Rows per page — mirrors the API's default page size. */
const PAGE_SIZE = 12;

/**
 * Accumulate `{ value: slug, label: name }` options seen in brand results,
 * without ever dropping a previously seen one. This is the *fallback* source
 * for the filter dropdown when the industries endpoint is unavailable; the API
 * only returns rows for the active filter, so deriving options purely from the
 * current page would otherwise collapse the choices once a filter is applied.
 */
export function mergeSeenIndustries(known, rows) {
  const bySlug = new Map(known.map((opt) => [opt.value, opt.label]));
  let changed = false;
  for (const row of rows) {
    if (row && row.industry_slug && !bySlug.has(row.industry_slug)) {
      bySlug.set(row.industry_slug, row.industry || row.industry_slug);
      changed = true;
    }
  }
  if (!changed) return known;
  return Array.from(bySlug, ([value, label]) => ({ value, label }));
}

export default function BrandList() {
  const { filters, setFilters } = useUrlSyncedFilters();

  // After a *user-initiated* change lands, move focus to the results region so
  // keyboard/screen-reader users are taken to the updated content instead of
  // being stranded on the control they just changed. Never fires on mount.
  const resultsRef = useRef(null);
  const pendingFocusRef = useRef(false);

  const changeFilters = (patch) => {
    pendingFocusRef.current = true;
    setFilters(patch); // resets page to 1 for filter/sort changes
  };

  const changePage = (nextPage) => {
    pendingFocusRef.current = true;
    setFilters({ page: nextPage });
  };

  // Query mirrors the URL state (page included), so the page number survives a
  // refresh and is shareable.
  const query = useMemo(
    () => ({
      industry: filters.industry,
      sort: filters.sort,
      dir: filters.dir,
      page: filters.page,
      pageSize: PAGE_SIZE,
    }),
    [filters.industry, filters.sort, filters.dir, filters.page],
  );

  const { status, data, error, retry } = useBrands(query);

  // Primary source of filter options: the dedicated industries endpoint.
  const { industries, failed: industriesFailed } = useIndustries();

  // Fallback source: industries observed in brand results (accumulated).
  const [seenIndustries, setSeenIndustries] = useState([]);
  useEffect(() => {
    const rows = data && Array.isArray(data.results) ? data.results : [];
    if (rows.length === 0) return;
    setSeenIndustries((known) => mergeSeenIndustries(known, rows));
  }, [data]);

  // Union the endpoint options with any seen in results, endpoint winning on
  // label, sorted by label for a stable dropdown order.
  const industryOptions = useMemo(() => {
    const bySlug = new Map();
    for (const ind of industries) {
      if (ind && ind.slug) bySlug.set(ind.slug, ind.name || ind.slug);
    }
    for (const opt of seenIndustries) {
      if (!bySlug.has(opt.value)) bySlug.set(opt.value, opt.label);
    }
    return Array.from(bySlug, ([value, label]) => ({ value, label })).sort(
      (a, b) => a.label.localeCompare(b.label),
    );
  }, [industries, seenIndustries]);

  // Once a settled result set arrives after a user interaction, move focus to
  // the results region (its aria-live count announces the change too).
  useEffect(() => {
    if (!pendingFocusRef.current) return;
    if (status === BrandsStatus.LOADING) return;
    if (resultsRef.current) resultsRef.current.focus();
    pendingFocusRef.current = false;
  }, [status, data]);

  const results = data && Array.isArray(data.results) ? data.results : [];
  const totalCount = data && typeof data.count === "number" ? data.count : null;

  const activeIndustry = filters.industry
    ? industryOptions.find((opt) => opt.value === filters.industry)
    : null;
  const activeIndustryLabel = activeIndustry
    ? activeIndustry.label
    : filters.industry || null;

  const showCount = status === BrandsStatus.SUCCESS && totalCount != null;

  return (
    <section className="brand-list" aria-label="Brand listing">
      <div className="brand-list__toolbar">
        <div className="brand-list__controls">
          <FilterControl
            value={filters.industry}
            options={industryOptions}
            onChange={(industry) => changeFilters({ industry })}
          />
          <SortControl
            sort={filters.sort}
            dir={filters.dir}
            onChange={({ sort, dir }) => changeFilters({ sort, dir })}
          />
          {industriesFailed && industryOptions.length === 0 ? (
            <p className="control__hint" role="status">
              Industry list unavailable — options will appear as brands load.
            </p>
          ) : null}
        </div>

        {showCount || activeIndustryLabel ? (
          <div className="brand-list__meta">
            {showCount ? (
              <span className="brand-list__count" aria-live="polite">
                {totalCount} {totalCount === 1 ? "brand" : "brands"}
              </span>
            ) : null}
            {activeIndustryLabel ? (
              <span className="filter-chip">
                {activeIndustryLabel}
                <button
                  type="button"
                  aria-label={`Clear ${activeIndustryLabel} filter`}
                  onClick={() => changeFilters({ industry: "" })}
                >
                  {"\u00d7"}
                </button>
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      <div
        className="brand-list__results"
        ref={resultsRef}
        tabIndex={-1}
        aria-label="Brand results"
      >
        {status === BrandsStatus.LOADING ? <Loading /> : null}
        {status === BrandsStatus.EMPTY ? <Empty /> : null}
        {status === BrandsStatus.ERROR ? (
          <Error message={error ? error.message : undefined} onRetry={retry} />
        ) : null}

        {status === BrandsStatus.SUCCESS ? (
          <>
            <div className="grid">
              {results.map((brand) => (
                <BrandCard key={brand.slug} brand={brand} />
              ))}
            </div>
            <Pagination
              page={filters.page}
              totalCount={data ? data.count : 0}
              pageSize={PAGE_SIZE}
              onPageChange={changePage}
            />
          </>
        ) : null}
      </div>
    </section>
  );
}

/**
 * Build a windowed list of page items: always the first and last page, the
 * current page ±`radius`, and `"ellipsis"` markers for the gaps. Keeps the DOM
 * bounded (~9 items) no matter how many pages exist.
 */
export function pageWindow(current, total, radius = 1) {
  const wanted = new Set([1, total]);
  for (let p = current - radius; p <= current + radius; p += 1) {
    if (p >= 1 && p <= total) wanted.add(p);
  }
  const sorted = Array.from(wanted).sort((a, b) => a - b);
  const items = [];
  let prev = 0;
  for (const p of sorted) {
    if (p - prev > 1) items.push("ellipsis");
    items.push(p);
    prev = p;
  }
  return items;
}

/**
 * Page-number pagination matching the reference theme's `.pagination` styling.
 * Windowed (first/last + current±1 + ellipses) so the control stays compact
 * even with many pages. Renders nothing when everything fits on a single page.
 */
function Pagination({ page, totalCount, pageSize, onPageChange }) {
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  if (totalPages <= 1) return null;

  const items = pageWindow(page, totalPages);

  return (
    <nav className="pagination" aria-label="Brand list pages">
      <button
        type="button"
        className="page-numbers"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
      >
        Previous
      </button>
      {items.map((item, i) =>
        item === "ellipsis" ? (
          <span
            key={`gap-${i}`}
            className="page-numbers dots"
            aria-hidden="true"
          >
            {"\u2026"}
          </span>
        ) : (
          <button
            key={item}
            type="button"
            className={item === page ? "page-numbers current" : "page-numbers"}
            aria-current={item === page ? "page" : undefined}
            aria-label={`Page ${item}`}
            onClick={() => onPageChange(item)}
          >
            {item}
          </button>
        ),
      )}
      <button
        type="button"
        className="page-numbers"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
      >
        Next
      </button>
    </nav>
  );
}
