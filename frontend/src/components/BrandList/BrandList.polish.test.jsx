/**
 * Tests for the BrandList presentation polish: results count, the active
 * industry filter chip (with clear action), and skeleton loading.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import BrandList from "./BrandList.jsx";

// Stub the industries hook so options come from results and no extra fetch runs.
vi.mock("../../hooks/useIndustries.js", () => ({
  useIndustries: () => ({ industries: [], failed: false }),
}));

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

function okFetch(results) {
  return vi.fn().mockResolvedValue(pageResponse(results));
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("BrandList — results count", () => {
  it("shows the total brand count on success", async () => {
    vi.stubGlobal("fetch", okFetch(SAMPLE_BRANDS));
    render(<BrandList />);

    await waitFor(() => {
      expect(screen.getByText(/2 brands/i)).toBeInTheDocument();
    });
  });

  it("uses the singular form for a single result", async () => {
    vi.stubGlobal("fetch", okFetch([SAMPLE_BRANDS[0]]));
    render(<BrandList />);

    await waitFor(() => {
      expect(screen.getByText(/^1 brand$/i)).toBeInTheDocument();
    });
  });
});

describe("BrandList — active filter chip", () => {
  it("shows a chip for the selected industry and clears it on demand", async () => {
    const fetchMock = okFetch(SAMPLE_BRANDS);
    vi.stubGlobal("fetch", fetchMock);
    render(<BrandList />);

    await waitFor(() => {
      expect(screen.getAllByRole("article")).toHaveLength(SAMPLE_BRANDS.length);
    });

    // The industry options are populated from the first result set via a
    // post-commit effect; wait for the option before selecting it.
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: "Insurance" }),
      ).toBeInTheDocument();
    });

    // Select an industry — a clear-filter chip appears.
    await userEvent.selectOptions(screen.getByLabelText(/industry/i), "insurance");
    const clearButton = await screen.findByRole("button", {
      name: /clear insurance filter/i,
    });

    // Clearing the chip resets the filter and the URL param.
    await userEvent.click(clearButton);
    await waitFor(() => {
      expect(
        new URLSearchParams(window.location.search).get("industry"),
      ).toBeNull();
    });
    expect(screen.getByLabelText(/industry/i)).toHaveValue("");
  });
});

describe("BrandList — skeleton loading", () => {
  it("renders skeleton cards (not real articles) while loading", () => {
    // A fetch that never resolves keeps the component in the loading state.
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    const { container } = render(<BrandList />);

    // Accessible status text is present for assistive tech.
    expect(screen.getByText(/loading brands/i)).toBeInTheDocument();
    // Skeleton placeholders render, and no real brand cards exist yet.
    expect(container.querySelectorAll(".skeleton-card").length).toBeGreaterThan(0);
    expect(screen.queryAllByRole("article")).toHaveLength(0);
  });
});
