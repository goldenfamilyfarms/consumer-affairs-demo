/**
 * Accessibility and responsive tests for <BrandList /> (Task 10.5).
 *
 * Covers:
 *   - filter/sort controls are labelled and keyboard-operable (Req 12.9, 12.10)
 *   - the star rating exposes an accessible text value (Req 12.9)
 *   - `axe` finds no violations in the rendered states (Req 12.9)
 *   - the responsive grid collapses to a single column at ≤640px (Req 12.11)
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";

import BrandList from "./BrandList.jsx";
import BrandCard from "./BrandCard.jsx";

// Stub the industries hook so these tests don't issue the extra endpoint fetch.
vi.mock("../../hooks/useIndustries.js", () => ({
  useIndustries: () => ({ industries: [], failed: false }),
}));

expect.extend(toHaveNoViolations);

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

describe("BrandList — controls are labelled and keyboard-operable", () => {
  it("associates a label with every control (Req 12.9)", async () => {
    vi.stubGlobal("fetch", okFetch(SAMPLE_BRANDS));
    render(<BrandList />);

    await waitFor(() => {
      expect(screen.getAllByRole("article")).toHaveLength(SAMPLE_BRANDS.length);
    });

    // getByLabelText only resolves when the control has an associated label.
    const industry = screen.getByLabelText(/industry/i);
    const sort = screen.getByLabelText(/sort by/i);

    // Native <select> elements are keyboard-operable by default (Req 12.10).
    expect(industry.tagName).toBe("SELECT");
    expect(sort.tagName).toBe("SELECT");
  });

  it("lets a keyboard user tab to and operate the controls (Req 12.10)", async () => {
    const fetchMock = okFetch(SAMPLE_BRANDS);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<BrandList />);

    await waitFor(() => {
      expect(screen.getAllByRole("article")).toHaveLength(SAMPLE_BRANDS.length);
    });

    // Tab from the document body reaches the first control (the filter).
    await user.tab();
    expect(screen.getByLabelText(/industry/i)).toHaveFocus();

    // Operating the focused control via the keyboard issues a new request.
    await user.selectOptions(document.activeElement, "insurance");
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    expect(fetchMock.mock.calls[1][0]).toContain("industry=insurance");
  });
});

describe("BrandCard — star rating exposes an accessible text value", () => {
  it("labels the rated stars with a numeric out-of-five value (Req 12.9)", () => {
    render(<BrandCard brand={SAMPLE_BRANDS[0]} />);

    // The stars container carries an accessible name describing the value.
    expect(
      screen.getByLabelText(/average rating: 4\.2 out of 5/i),
    ).toBeInTheDocument();
    // The same value is available as text in the accessibility tree.
    expect(screen.getByText(/average rating: 4\.2 out of 5/i)).toBeInTheDocument();
  });

  it("exposes a text value for zero-review brands with no rating (Req 12.9)", () => {
    const zeroReview = {
      ...SAMPLE_BRANDS[0],
      average_rating: null,
      review_count: 0,
    };
    render(<BrandCard brand={zeroReview} />);

    expect(screen.getByLabelText(/no ratings yet/i)).toBeInTheDocument();
  });
});

describe("BrandList — axe accessibility audit of rendered states", () => {
  it("has no violations in the success state", async () => {
    vi.stubGlobal("fetch", okFetch(SAMPLE_BRANDS));
    const { container } = render(<BrandList />);

    await waitFor(() => {
      expect(screen.getAllByRole("article")).toHaveLength(SAMPLE_BRANDS.length);
    });

    expect(await axe(container)).toHaveNoViolations();
  });

  it("has no violations in the empty state", async () => {
    vi.stubGlobal("fetch", okFetch([]));
    const { container } = render(<BrandList />);

    await waitFor(() => {
      expect(screen.getByText(/no brands match/i)).toBeInTheDocument();
    });

    expect(await axe(container)).toHaveNoViolations();
  });

  it("has no violations in the error state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: "boom" }),
      }),
    );
    const { container } = render(<BrandList />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("BrandList — responsive grid", () => {
  it("lays cards out with the reference .grid container (Req 12.11)", async () => {
    vi.stubGlobal("fetch", okFetch(SAMPLE_BRANDS));
    const { container } = render(<BrandList />);

    await waitFor(() => {
      expect(screen.getAllByRole("article")).toHaveLength(SAMPLE_BRANDS.length);
    });

    const grid = container.querySelector(".grid");
    expect(grid).not.toBeNull();
    // Every card lives inside the responsive grid.
    expect(grid.querySelectorAll(".card")).toHaveLength(SAMPLE_BRANDS.length);
  });

  it("collapses the grid to a single column at ≤640px in the compiled CSS (Req 12.11)", () => {
    const cssPath = path.resolve(
      path.dirname(fileURLToPath(import.meta.url)),
      "../../../static/css/theme.css",
    );
    const css = readFileSync(cssPath, "utf8");

    // The compiled theme carries the mobile breakpoint that collapses the grid.
    expect(css).toMatch(/@media\s*\(max-width:\s*640px\)/);

    // Within a 640px media block, the grid becomes a single column.
    const mobileBlocks = css.match(
      /@media\s*\(max-width:\s*640px\)\s*\{[\s\S]*?\n\}/g,
    );
    expect(mobileBlocks).not.toBeNull();
    const collapsesGrid = mobileBlocks.some(
      (block) =>
        block.includes(".grid") &&
        /grid-template-columns:\s*1fr/.test(block),
    );
    expect(collapsesGrid).toBe(true);
  });
});
