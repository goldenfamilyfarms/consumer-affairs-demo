/**
 * Unit tests for the windowed pagination helper. It keeps the rendered control
 * bounded regardless of page count: always first + last, current ±radius, and
 * "ellipsis" markers for the gaps.
 */

import { describe, it, expect } from "vitest";

import { pageWindow } from "./BrandList.jsx";

describe("pageWindow", () => {
  it("returns every page when there are no gaps", () => {
    expect(pageWindow(1, 3)).toEqual([1, 2, 3]);
  });

  it("inserts ellipses around a middle page in a large range", () => {
    // current=50 of 100, radius 1 → 1 … 49 50 51 … 100
    expect(pageWindow(50, 100)).toEqual([1, "ellipsis", 49, 50, 51, "ellipsis", 100]);
  });

  it("has no leading ellipsis near the start", () => {
    expect(pageWindow(2, 100)).toEqual([1, 2, 3, "ellipsis", 100]);
  });

  it("has no trailing ellipsis near the end", () => {
    expect(pageWindow(99, 100)).toEqual([1, "ellipsis", 98, 99, 100]);
  });

  it("stays compact (<= ~7 items) even for very large page counts", () => {
    expect(pageWindow(500, 1000).length).toBeLessThanOrEqual(7);
  });

  it("never duplicates the first/last page when current is at an edge", () => {
    const items = pageWindow(1, 10);
    expect(items.filter((x) => x === 1)).toHaveLength(1);
    expect(items.filter((x) => x === 10)).toHaveLength(1);
  });
});
