/**
 * Component state tests for <BrandList /> (Task 10.4).
 *
 * Drives the component through its full request lifecycle by stubbing the
 * global `fetch` (BrandList → useBrands → fetchBrands → fetch). Covers:
 *   - loading → success renders one card per row (Req 12.2, 12.3)
 *   - empty state when zero rows are returned (Req 12.4)
 *   - error state + retry re-issues the request (Req 12.5)
 *   - filter change triggers a filtered fetch (Req 12.6)
 *   - sort change triggers a sorted fetch (Req 12.7)
 *   - control changes update the URL query string, and state initializes
 *     from the URL query params on mount (Req 12.8)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import BrandList from "./BrandList.jsx";

// The industries endpoint is exercised in its own tests; stub the hook here so
// these tests only count /api/brands/ fetches. Options then come from results.
vi.mock("../../hooks/useIndustries.js", () => ({
  useIndustries: () => ({ industries: [], failed: false }),
}));

/** Two brands across two industries, enough to populate the filter options. */
const SAMPLE_BRANDS = [
  {
    name: "Acme Insurance Co.",
    slug: "acme-insurance",
    industry: "Insurance",
    industry_slug: "insurance",
    average_rating: 4.17,
    review_count: 12,
    short_description: "A long-running general-lines insurer.",
    top_review_snippet: "Filed a claim after a storm...",
  },
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

/** Build an ok JSON Response-like object wrapping the given result rows. */
function pageResponse(results) {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      count: results.length,
      next: null,
      previous: null,
      results,
    }),
  };
}

/** A fetch mock that always resolves an ok page with the given rows. */
function okFetch(results) {
  return vi.fn().mockResolvedValue(pageResponse(results));
}

/** Extract the URL string from the Nth call to the fetch mock. */
function callUrl(fetchMock, index) {
  return fetchMock.mock.calls[index][0];
}

beforeEach(() => {
  // Start every test from a clean URL so the URL-synced filters initialize
  // predictably (Req 12.8).
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("BrandList — loading and success", () => {
  it("shows the loading state, then renders one card per returned row", async () => {
    const fetchMock = okFetch(SAMPLE_BRANDS);
    vi.stubGlobal("fetch", fetchMock);

    render(<BrandList />);

    // Loading is shown while the request is in flight (Req 12.2).
    expect(screen.getByText(/loading brands/i)).toBeInTheDocument();

    // Success renders exactly one card (semantic <article>) per row (Req 12.3).
    await waitFor(() => {
      expect(screen.getAllByRole("article")).toHaveLength(SAMPLE_BRANDS.length);
    });
    expect(
      screen.getByRole("heading", { name: /acme insurance co\./i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /first national bank/i }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("BrandList — empty state", () => {
  it("shows the empty state when the API returns zero rows", async () => {
    const fetchMock = okFetch([]);
    vi.stubGlobal("fetch", fetchMock);

    render(<BrandList />);

    await waitFor(() => {
      expect(screen.getByText(/no brands match/i)).toBeInTheDocument();
    });
    expect(screen.queryAllByRole("article")).toHaveLength(0);
  });
});

describe("BrandList — error state and retry", () => {
  it("shows the error state on failure and recovers when retry succeeds", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: "boom" }),
      })
      .mockResolvedValueOnce(pageResponse(SAMPLE_BRANDS));
    vi.stubGlobal("fetch", fetchMock);

    render(<BrandList />);

    // Error region is announced via role="alert" (Req 12.5).
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    const retryButton = screen.getByRole("button", { name: /retry/i });

    await userEvent.click(retryButton);

    // Retry re-issues the request and transitions to success.
    await waitFor(() => {
      expect(screen.getAllByRole("article")).toHaveLength(SAMPLE_BRANDS.length);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("BrandList — filter change", () => {
  it("triggers a filtered fetch and updates the URL when an industry is picked", async () => {
    const fetchMock = okFetch(SAMPLE_BRANDS);
    vi.stubGlobal("fetch", fetchMock);

    render(<BrandList />);

    // Wait for the first load so the industry options are populated.
    await waitFor(() => {
      expect(screen.getAllByRole("article")).toHaveLength(SAMPLE_BRANDS.length);
    });
    expect(callUrl(fetchMock, 0)).not.toContain("industry=");

    const industrySelect = screen.getByLabelText(/industry/i);
    // The option's value is the industry slug (label "Insurance").
    await userEvent.selectOptions(industrySelect, "insurance");

    // A new request is issued carrying the selected industry slug (Req 12.6).
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    expect(callUrl(fetchMock, 1)).toContain("industry=insurance");

    // The URL query string reflects the selection (Req 12.8).
    expect(new URLSearchParams(window.location.search).get("industry")).toBe(
      "insurance",
    );
  });
});

describe("BrandList — sort change", () => {
  it("triggers a sorted fetch and updates the URL when the sort key changes", async () => {
    const fetchMock = okFetch(SAMPLE_BRANDS);
    vi.stubGlobal("fetch", fetchMock);

    render(<BrandList />);

    await waitFor(() => {
      expect(screen.getAllByRole("article")).toHaveLength(SAMPLE_BRANDS.length);
    });

    const sortSelect = screen.getByLabelText(/sort by/i);
    // The consolidated control encodes key + direction in one option value.
    await userEvent.selectOptions(sortSelect, "avg_rating:desc");

    // A new request is issued ordered by the chosen key + direction (Req 12.7).
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    expect(callUrl(fetchMock, 1)).toContain("sort=avg_rating");
    expect(callUrl(fetchMock, 1)).toContain("dir=desc");

    // The URL query string reflects the selection (Req 12.8).
    const params = new URLSearchParams(window.location.search);
    expect(params.get("sort")).toBe("avg_rating");
    expect(params.get("dir")).toBe("desc");
  });
});

describe("BrandList — initialize from URL", () => {
  it("reads the filter/sort/direction params from the URL on mount", async () => {
    window.history.replaceState(
      null,
      "",
      "/?industry=insurance&sort=avg_rating&dir=asc",
    );
    const fetchMock = okFetch(SAMPLE_BRANDS);
    vi.stubGlobal("fetch", fetchMock);

    render(<BrandList />);

    // The very first request already carries the URL-derived params (Req 12.8).
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    const firstUrl = callUrl(fetchMock, 0);
    expect(firstUrl).toContain("industry=insurance");
    expect(firstUrl).toContain("sort=avg_rating");
    expect(firstUrl).toContain("dir=asc");

    // The controls render initialized to the URL state.
    await waitFor(() => {
      expect(screen.getAllByRole("article")).toHaveLength(SAMPLE_BRANDS.length);
    });
    // The consolidated sort control reflects key + direction as one value.
    expect(screen.getByLabelText(/sort by/i)).toHaveValue("avg_rating:asc");
    expect(screen.getByLabelText(/industry/i)).toHaveValue("insurance");
  });
});
