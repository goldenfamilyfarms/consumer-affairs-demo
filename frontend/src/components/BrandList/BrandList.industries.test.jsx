/**
 * Tests for the industry filter's data source. The dropdown is populated from a
 * dedicated `/api/industries/` endpoint (via useIndustries), so it's complete
 * even on a cold `?industry=…` load or after a filter narrows the results —
 * with graceful fallback to result-derived options if that endpoint fails.
 *
 * These tests intentionally do NOT mock useIndustries; they stub `fetch` and
 * discriminate by URL.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import BrandList from "./BrandList.jsx";

const ALL_INDUSTRIES = [
  { name: "Banking", slug: "banking", brand_count: 1 },
  { name: "Insurance", slug: "insurance", brand_count: 3 },
  { name: "Retail", slug: "retail", brand_count: 2 },
];

const BANKING_ONLY = [
  {
    name: "First National Bank",
    slug: "first-national-bank",
    industry: "Banking",
    industry_slug: "banking",
    average_rating: 3.5,
    review_count: 8,
    short_description: "A regional retail bank.",
    top_review_snippet: "Opening an account was quick...",
  },
];

/** A fetch stub that returns industries for the industries endpoint and a
 * brand page for the brands endpoint. `brandsFails`/`industriesFails` flip
 * either to a rejected/500 response. */
function makeFetch({ industries = ALL_INDUSTRIES, brands = BANKING_ONLY, industriesFails = false } = {}) {
  return vi.fn((url) => {
    if (String(url).includes("/api/industries/")) {
      if (industriesFails) {
        return Promise.resolve({ ok: false, status: 500, json: async () => ({}) });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => industries });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ count: brands.length, next: null, previous: null, results: brands }),
    });
  });
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("BrandList — industry filter options", () => {
  it("shows all industries on a cold ?industry=banking load, even though results are filtered", async () => {
    window.history.replaceState(null, "", "/?industry=banking");
    vi.stubGlobal("fetch", makeFetch());

    render(<BrandList />);

    // The full set is available from the endpoint, not just the filtered result.
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Insurance" })).toBeInTheDocument();
    });
    expect(screen.getByRole("option", { name: "Retail" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Banking" })).toBeInTheDocument();

    // And the active filter is reflected as the selected value.
    expect(screen.getByLabelText(/industry/i)).toHaveValue("banking");
  });

  it("falls back to result-derived options when the industries endpoint fails", async () => {
    vi.stubGlobal("fetch", makeFetch({ industriesFails: true }));

    render(<BrandList />);

    // Banking came from the brand results even though the endpoint 500'd.
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Banking" })).toBeInTheDocument();
    });
  });
});
