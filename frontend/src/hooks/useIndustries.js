/**
 * Loads the full set of industries once on mount so the filter dropdown is
 * complete from the first render — even on a cold load with `?industry=banking`
 * already in the URL, and even after a filter narrows the brand results.
 *
 * The fetch is non-critical: if it fails, the BrandList falls back to
 * accumulating industries seen in the brand results. But we surface a `failed`
 * flag so the UI can show a subtle notice when the dropdown is (temporarily)
 * incomplete, rather than silently presenting an empty filter.
 *
 * @returns {{ industries: Array<{name: string, slug: string, brand_count?: number}>, failed: boolean }}
 */

import { useEffect, useState } from "react";

import { fetchIndustries } from "../api/industries.js";

export function useIndustries() {
  const [state, setState] = useState({ industries: [], failed: false });

  useEffect(() => {
    const controller = new AbortController();
    fetchIndustries({ signal: controller.signal })
      .then((rows) => {
        if (!controller.signal.aborted) {
          setState({ industries: rows, failed: false });
        }
      })
      .catch((err) => {
        // Ignore cancellations; flag real failures so the UI can hint at the
        // degraded (result-derived) filter options.
        if (controller.signal.aborted || (err && err.name === "AbortError")) return;
        setState({ industries: [], failed: true });
      });
    return () => controller.abort();
  }, []);

  return state;
}
