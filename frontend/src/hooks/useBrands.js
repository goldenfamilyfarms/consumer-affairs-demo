/**
 * Data-fetching hook for the BrandList component (Requirements 12.1, 12.6, 12.7).
 *
 * `useBrands` owns the request lifecycle as an explicit status enum:
 *
 *   loading  → a request is in flight
 *   success  → the request returned one or more brand rows
 *   empty    → the request returned zero brand rows
 *   error    → the request failed (non-2xx or network error)
 *
 * It fetches on mount (Req 12.1) and re-fetches whenever the query params
 * change (Req 12.6 filter change, Req 12.7 sort change). In-flight requests are
 * abortable via `AbortController`, so rapid filter/sort changes cancel the
 * previous request instead of racing it. Aborted requests never transition the
 * hook into the error state.
 *
 * @typedef {import("../api/brands.js").BrandQuery} BrandQuery
 * @typedef {import("../api/brands.js").BrandPage} BrandPage
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchBrands } from "../api/brands.js";

/** The request-lifecycle status values (Requirement 12.2–12.5). */
export const BrandsStatus = Object.freeze({
  LOADING: "loading",
  SUCCESS: "success",
  EMPTY: "empty",
  ERROR: "error",
});

/**
 * Fetch a page of brand rows, tracking loading/success/empty/error state.
 *
 * @param {BrandQuery} [query]  Filter/sort/pagination params. Changing the
 *   param values triggers a re-fetch and cancels any in-flight request.
 * @param {{ baseUrl?: string, fetchFn?: typeof fetch }} [options]  Passed
 *   through to `fetchBrands` (used by tests to inject a fetch implementation).
 * @returns {{
 *   status: "loading" | "success" | "empty" | "error",
 *   data: BrandPage | null,
 *   error: Error | null,
 *   retry: () => void,
 * }}
 */
export function useBrands(query = {}, options = {}) {
  const [state, setState] = useState({
    status: BrandsStatus.LOADING,
    data: null,
    error: null,
  });

  // Bump this to force a re-fetch (used by the error-state retry action).
  const [reloadToken, setReloadToken] = useState(0);

  // Stable dependency: re-run the effect only when param *values* change, not
  // when the caller passes a fresh object literal on every render.
  const queryKey = JSON.stringify(query ?? {});

  // Keep the latest query/options available to the effect without adding the
  // object identities to the dependency array.
  const latest = useRef({ query, options });
  latest.current = { query, options };

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: BrandsStatus.LOADING, data: null, error: null });

    const { query: currentQuery, options: currentOptions } = latest.current;

    fetchBrands(currentQuery, { ...currentOptions, signal: controller.signal })
      .then((page) => {
        if (controller.signal.aborted) return;
        const results =
          page && Array.isArray(page.results) ? page.results : [];
        setState({
          status: results.length === 0 ? BrandsStatus.EMPTY : BrandsStatus.SUCCESS,
          data: page,
          error: null,
        });
      })
      .catch((error) => {
        // Ignore cancellations; a superseding request or unmount aborted us.
        if (controller.signal.aborted || (error && error.name === "AbortError")) {
          return;
        }
        setState({ status: BrandsStatus.ERROR, data: null, error });
      });

    return () => controller.abort();
    // `queryKey` captures param-value changes; `reloadToken` drives retry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey, reloadToken]);

  const retry = useCallback(() => {
    setReloadToken((token) => token + 1);
  }, []);

  return { ...state, retry };
}
