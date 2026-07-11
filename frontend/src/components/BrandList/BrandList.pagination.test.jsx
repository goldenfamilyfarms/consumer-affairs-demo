/**
 * Tests that the page number is URL-synced: it initializes from the URL (so a
 * refresh on page 3 stays on page 3) and updates the URL when the user paginates.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import BrandList from "./BrandList.jsx";

// Industries come from the endpoint elsewhere; stub the hook here.
vi.mock("../../hooks/useIndustries.js", () => ({
  useIndustries: () => ({ industries: [], failed: false }),
}));

const ROWS = Array.from({ length: 12 }, (_, i) => ({
  name: `Brand ${i}`,
  slug: `brand-${i}`,
  industry: "Insurance",
  industry_slug: "insurance",
  average_rating: 4,
  review_count: 5,
  short_description: "A brand.",
  top_review_snippet: "Good.",
}));

/** Fetch stub reporting a large total so pagination renders (>1 page). */
function pagedFetch(count) {
  return vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ count, next: null, previous: null, results: ROWS }),
    }),
  );
}

function callUrl(mock, i) {
  return mock.mock.calls[i][0];
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("BrandList — page is URL-synced", () => {
  it("initializes the page from the URL on mount", async () => {
    window.history.replaceState(null, "", "/?page=2");
    const fetchMock = pagedFetch(30);
    vi.stubGlobal("fetch", fetchMock);

    render(<BrandList />);

    // The very first request carries page=2 (a refresh on page 2 stays there).
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(callUrl(fetchMock, 0)).toContain("page=2");
  });

  it("updates the URL and refetches when the user changes page", async () => {
    const fetchMock = pagedFetch(30); // 30 / 12 => 3 pages
    vi.stubGlobal("fetch", fetchMock);

    render(<BrandList />);

    await waitFor(() => {
      expect(screen.getAllByRole("article")).toHaveLength(ROWS.length);
    });

    // Pagination is present because count > page size. Buttons are labelled
    // "Page N" for assistive tech.
    await userEvent.click(screen.getByRole("button", { name: "Page 2" }));

    await waitFor(() => {
      expect(
        new URLSearchParams(window.location.search).get("page"),
      ).toBe("2");
    });
    // A new request was issued for page 2.
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((c) => String(c[0]).includes("page=2")),
      ).toBe(true);
    });
  });
});
