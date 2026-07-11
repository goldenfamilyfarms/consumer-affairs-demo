import { describe, it, expect, vi } from "vitest";
import {
  buildBrandsQuery,
  fetchBrands,
  BrandApiError,
  BRANDS_ENDPOINT,
} from "./brands.js";

describe("buildBrandsQuery", () => {
  it("returns an empty string when no params are provided", () => {
    expect(buildBrandsQuery()).toBe("");
    expect(buildBrandsQuery({})).toBe("");
  });

  it("serializes industry/sort/dir/page and maps pageSize to page_size", () => {
    const qs = buildBrandsQuery({
      industry: "insurance",
      sort: "avg_rating",
      dir: "desc",
      page: 2,
      pageSize: 12,
    });
    const params = new URLSearchParams(qs.slice(1));
    expect(params.get("industry")).toBe("insurance");
    expect(params.get("sort")).toBe("avg_rating");
    expect(params.get("dir")).toBe("desc");
    expect(params.get("page")).toBe("2");
    expect(params.get("page_size")).toBe("12");
  });

  it("omits undefined params so the API applies defaults", () => {
    expect(buildBrandsQuery({ sort: "review_count" })).toBe("?sort=review_count");
  });
});

describe("fetchBrands", () => {
  const page = {
    count: 1,
    next: null,
    previous: null,
    results: [
      {
        name: "Acme Insurance Co.",
        slug: "acme-insurance",
        industry: "Insurance",
        average_rating: 4.17,
        review_count: 12,
        short_description: "Acme Insurance is a long-running insurer...",
        top_review_snippet: "Filed a claim after a storm...",
      },
    ],
  };

  it("requests the endpoint with the built query string and returns the page", async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => page,
    });

    const result = await fetchBrands(
      { industry: "insurance", sort: "avg_rating", dir: "desc", page: 1, pageSize: 12 },
      { fetchFn },
    );

    expect(result).toEqual(page);
    const calledUrl = fetchFn.mock.calls[0][0];
    expect(calledUrl.startsWith(`${BRANDS_ENDPOINT}?`)).toBe(true);
    expect(calledUrl).toContain("industry=insurance");
    expect(calledUrl).toContain("page_size=12");
  });

  it("throws BrandApiError with the API detail message on a 400 response", async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Invalid filter value" }),
    });

    await expect(fetchBrands({ industry: "nope" }, { fetchFn })).rejects.toMatchObject({
      name: "BrandApiError",
      status: 400,
      detail: "Invalid filter value",
    });
  });

  it("wraps network failures in a BrandApiError", async () => {
    const fetchFn = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(fetchBrands({}, { fetchFn })).rejects.toBeInstanceOf(BrandApiError);
  });

  it("re-throws AbortError so cancellation is distinguishable", async () => {
    const abortError = Object.assign(new Error("aborted"), { name: "AbortError" });
    const fetchFn = vi.fn().mockRejectedValue(abortError);
    await expect(fetchBrands({}, { fetchFn })).rejects.toMatchObject({ name: "AbortError" });
  });
});
