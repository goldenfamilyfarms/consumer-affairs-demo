import { describe, it, expect, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import {
  useUrlSyncedFilters,
  readFiltersFromSearch,
  buildFilterSearch,
} from "./useUrlSyncedFilters.js";

beforeEach(() => {
  // Reset the URL to a clean path between tests.
  window.history.replaceState(null, "", "/");
});

describe("readFiltersFromSearch", () => {
  it("extracts the synced params, defaulting missing ones", () => {
    expect(
      readFiltersFromSearch("?industry=insurance&sort=avg_rating&dir=desc&page=3"),
    ).toEqual({
      industry: "insurance",
      sort: "avg_rating",
      dir: "desc",
      page: 3,
    });
    expect(readFiltersFromSearch("?page=2")).toEqual({
      industry: "",
      sort: "",
      dir: "",
      page: 2,
    });
  });

  it("normalizes an invalid or ≤1 page to 1", () => {
    expect(readFiltersFromSearch("").page).toBe(1);
    expect(readFiltersFromSearch("?page=0").page).toBe(1);
    expect(readFiltersFromSearch("?page=abc").page).toBe(1);
    expect(readFiltersFromSearch("?page=1").page).toBe(1);
  });
});

describe("buildFilterSearch", () => {
  it("sets active params, deletes empty ones, and keeps page>1", () => {
    const qs = buildFilterSearch("", {
      industry: "insurance",
      sort: "",
      dir: "desc",
      page: 2,
    });
    const params = new URLSearchParams(qs.slice(1));
    expect(params.get("industry")).toBe("insurance");
    expect(params.get("dir")).toBe("desc");
    expect(params.has("sort")).toBe(false);
    expect(params.get("page")).toBe("2");
  });

  it("omits page when it is 1 (clean URLs)", () => {
    const qs = buildFilterSearch("", {
      industry: "insurance",
      sort: "",
      dir: "",
      page: 1,
    });
    expect(new URLSearchParams(qs.slice(1)).has("page")).toBe(false);
  });

  it("returns an empty string when no params remain", () => {
    expect(
      buildFilterSearch("", { industry: "", sort: "", dir: "", page: 1 }),
    ).toBe("");
  });
});

describe("useUrlSyncedFilters", () => {
  it("reads the initial filters (including page) from the URL", () => {
    window.history.replaceState(null, "", "/?industry=banking&sort=review_count&page=2");
    const { result } = renderHook(() => useUrlSyncedFilters());
    expect(result.current.filters).toEqual({
      industry: "banking",
      sort: "review_count",
      dir: "",
      page: 2,
    });
  });

  it("writes a merged patch back to the URL via the History API", () => {
    const { result } = renderHook(() => useUrlSyncedFilters());

    act(() => result.current.setFilters({ industry: "insurance" }));

    expect(result.current.filters.industry).toBe("insurance");
    expect(new URLSearchParams(window.location.search).get("industry")).toBe("insurance");
  });

  it("clears a param when its value is emptied", () => {
    window.history.replaceState(null, "", "/?industry=insurance");
    const { result } = renderHook(() => useUrlSyncedFilters());

    act(() => result.current.setFilters({ industry: "" }));

    expect(result.current.filters.industry).toBe("");
    expect(window.location.search).toBe("");
  });

  it("resets page to 1 when a filter changes", () => {
    window.history.replaceState(null, "", "/?industry=banking&page=4");
    const { result } = renderHook(() => useUrlSyncedFilters());
    expect(result.current.filters.page).toBe(4);

    act(() => result.current.setFilters({ industry: "insurance" }));

    expect(result.current.filters.page).toBe(1);
    expect(new URLSearchParams(window.location.search).has("page")).toBe(false);
  });

  it("keeps filters intact when only the page changes", () => {
    window.history.replaceState(null, "", "/?industry=banking&sort=avg_rating");
    const { result } = renderHook(() => useUrlSyncedFilters());

    act(() => result.current.setFilters({ page: 3 }));

    expect(result.current.filters.industry).toBe("banking");
    expect(result.current.filters.sort).toBe("avg_rating");
    expect(result.current.filters.page).toBe(3);
    expect(new URLSearchParams(window.location.search).get("page")).toBe("3");
  });

  it("resyncs from the URL on popstate (back/forward navigation)", () => {
    const { result } = renderHook(() => useUrlSyncedFilters());

    act(() => result.current.setFilters({ industry: "banking" }));
    expect(result.current.filters.industry).toBe("banking");

    act(() => {
      window.history.replaceState(null, "", "/?industry=insurance");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    expect(result.current.filters.industry).toBe("insurance");
  });
});
