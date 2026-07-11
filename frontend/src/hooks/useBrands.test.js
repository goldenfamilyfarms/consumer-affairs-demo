import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useBrands, BrandsStatus } from "./useBrands.js";

/** Build a fake `fetch` that resolves an ok JSON response with `results`. */
function okFetch(results) {
  return vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ count: results.length, next: null, previous: null, results }),
  });
}

const sampleBrand = {
  name: "Acme Insurance Co.",
  slug: "acme-insurance",
  industry: "Insurance",
  average_rating: 4.17,
  review_count: 12,
  short_description: null,
  top_review_snippet: null,
};

describe("useBrands", () => {
  it("fetches on mount and resolves to success with the returned rows", async () => {
    const fetchFn = okFetch([sampleBrand]);
    const { result } = renderHook(() => useBrands({}, { fetchFn }));

    expect(result.current.status).toBe(BrandsStatus.LOADING);
    await waitFor(() => expect(result.current.status).toBe(BrandsStatus.SUCCESS));
    expect(result.current.data.results).toEqual([sampleBrand]);
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it("resolves to empty when the API returns zero rows", async () => {
    const fetchFn = okFetch([]);
    const { result } = renderHook(() => useBrands({}, { fetchFn }));

    await waitFor(() => expect(result.current.status).toBe(BrandsStatus.EMPTY));
    expect(result.current.data.results).toEqual([]);
  });

  it("resolves to error when the request fails", async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: "boom" }),
    });
    const { result } = renderHook(() => useBrands({}, { fetchFn }));

    await waitFor(() => expect(result.current.status).toBe(BrandsStatus.ERROR));
    expect(result.current.error).toBeTruthy();
  });

  it("re-fetches when the query params change", async () => {
    const fetchFn = okFetch([sampleBrand]);
    const { result, rerender } = renderHook(({ query }) => useBrands(query, { fetchFn }), {
      initialProps: { query: { industry: "insurance" } },
    });

    await waitFor(() => expect(result.current.status).toBe(BrandsStatus.SUCCESS));
    expect(fetchFn).toHaveBeenCalledTimes(1);

    rerender({ query: { industry: "banking" } });
    await waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(2));
    expect(fetchFn.mock.calls[1][0]).toContain("industry=banking");
  });

  it("does not re-fetch when a new query object has identical values", async () => {
    const fetchFn = okFetch([sampleBrand]);
    const { result, rerender } = renderHook(({ query }) => useBrands(query, { fetchFn }), {
      initialProps: { query: { industry: "insurance" } },
    });

    await waitFor(() => expect(result.current.status).toBe(BrandsStatus.SUCCESS));
    rerender({ query: { industry: "insurance" } });
    // Give any stray effect a chance to run.
    await Promise.resolve();
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it("retry() re-runs the fetch after an error", async () => {
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ count: 1, next: null, previous: null, results: [sampleBrand] }),
      });
    const { result } = renderHook(() => useBrands({}, { fetchFn }));

    await waitFor(() => expect(result.current.status).toBe(BrandsStatus.ERROR));
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe(BrandsStatus.SUCCESS));
    expect(fetchFn).toHaveBeenCalledTimes(2);
  });
});
