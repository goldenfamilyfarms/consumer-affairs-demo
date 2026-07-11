/**
 * URL-synced filter/sort/pagination state for the BrandList (Requirement 12.8).
 *
 * The browser URL query string is the single source of truth for the active
 * industry filter, sort key, sort direction, and page number. This hook reads
 * them out of `window.location.search` on mount, keeps them in sync with
 * back/forward navigation (`popstate`), and writes changes back through the
 * History API — so the full view state is shareable, bookmarkable, and
 * back-button friendly, including which page you were on.
 *
 * Key interaction: changing a filter or sort **resets the page to 1**, because
 * the old page number is meaningless against a different result set. Changing
 * only the page leaves the filters intact.
 *
 * @typedef {Object} SyncedFilters
 * @property {string} industry  Industry slug filter ("" when unset).
 * @property {string} sort      Sort key: "avg_rating" | "review_count" | "".
 * @property {string} dir       Sort direction: "asc" | "desc" | "".
 * @property {number} page      1-based page number (1 when unset).
 */

import { useCallback, useEffect, useState } from "react";

/** String query-string keys this hook owns. `page` is handled separately. */
export const FILTER_PARAM_KEYS = ["industry", "sort", "dir"];

/** Parse a 1-based page from a raw param; anything invalid or ≤1 becomes 1. */
function parsePage(raw) {
  const n = parseInt(raw, 10);
  return Number.isInteger(n) && n > 1 ? n : 1;
}

/**
 * Parse the synced params out of a query string.
 *
 * @param {string} search  A `location.search` value (may start with `?`).
 * @returns {SyncedFilters}
 */
export function readFiltersFromSearch(search) {
  const params = new URLSearchParams(search);
  return {
    industry: params.get("industry") || "",
    sort: params.get("sort") || "",
    dir: params.get("dir") || "",
    page: parsePage(params.get("page")),
  };
}

/**
 * Build a new query string applying the synced values. Empty string values and
 * `page <= 1` delete their key (so URLs stay clean and the API uses defaults);
 * any non-owned params already present are preserved.
 *
 * @param {string} currentSearch  The existing `location.search`.
 * @param {SyncedFilters} filters  The desired values.
 * @returns {string} A query string beginning with `?`, or an empty string.
 */
export function buildFilterSearch(currentSearch, filters) {
  const params = new URLSearchParams(currentSearch);

  for (const key of FILTER_PARAM_KEYS) {
    const value = filters[key];
    if (value) params.set(key, value);
    else params.delete(key);
  }

  if (filters.page && filters.page > 1) params.set("page", String(filters.page));
  else params.delete("page");

  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/**
 * React hook exposing the URL-synced state and a setter.
 *
 * @returns {{ filters: SyncedFilters, setFilters: (patch: Partial<SyncedFilters>) => void }}
 *   `setFilters` merges a partial patch; changing a filter/sort key resets
 *   `page` to 1 unless the patch sets `page` explicitly.
 */
export function useUrlSyncedFilters() {
  const [filters, setFiltersState] = useState(() =>
    readFiltersFromSearch(window.location.search),
  );

  useEffect(() => {
    const handlePopState = () => {
      setFiltersState(readFiltersFromSearch(window.location.search));
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const setFilters = useCallback((patch) => {
    setFiltersState((prev) => {
      const next = { ...prev, ...patch };

      // A filter/sort change invalidates the current page — reset to 1 unless
      // the caller explicitly set a page in the same patch.
      const changesFilter = FILTER_PARAM_KEYS.some(
        (key) => key in patch && patch[key] !== prev[key],
      );
      if (changesFilter && !("page" in patch)) next.page = 1;

      const search = buildFilterSearch(window.location.search, next);
      const url = `${window.location.pathname}${search}${window.location.hash}`;
      window.history.pushState(null, "", url);
      return next;
    });
  }, []);

  return { filters, setFilters };
}
