/**
 * Unit tests for the `mergeSeenIndustries` accumulator — the fallback source
 * for the filter dropdown. It runs on every brand result set, so its
 * behavior (dedupe by slug, never drop a seen option, and return the same
 * array reference when nothing changed) matters for correctness and renders.
 */

import { describe, it, expect } from "vitest";

import { mergeSeenIndustries } from "./BrandList.jsx";

const row = (slug, name) => ({ industry_slug: slug, industry: name });

describe("mergeSeenIndustries", () => {
  it("adds new { value: slug, label: name } options from rows", () => {
    const out = mergeSeenIndustries([], [row("insurance", "Insurance"), row("banking", "Banking")]);
    expect(out).toEqual([
      { value: "insurance", label: "Insurance" },
      { value: "banking", label: "Banking" },
    ]);
  });

  it("dedupes by slug within a single merge", () => {
    const out = mergeSeenIndustries([], [row("insurance", "Insurance"), row("insurance", "Insurance")]);
    expect(out).toHaveLength(1);
    expect(out[0]).toEqual({ value: "insurance", label: "Insurance" });
  });

  it("never drops a previously seen option", () => {
    const known = [{ value: "insurance", label: "Insurance" }];
    // A filtered page that only returns banking rows must not lose insurance.
    const out = mergeSeenIndustries(known, [row("banking", "Banking")]);
    const slugs = out.map((o) => o.value);
    expect(slugs).toContain("insurance");
    expect(slugs).toContain("banking");
  });

  it("returns the SAME array reference when nothing new is seen (render stability)", () => {
    const known = [{ value: "insurance", label: "Insurance" }];
    const out = mergeSeenIndustries(known, [row("insurance", "Insurance")]);
    expect(out).toBe(known);
  });

  it("ignores rows without an industry_slug", () => {
    const out = mergeSeenIndustries([], [{ industry: "No slug" }, row("retail", "Retail")]);
    expect(out).toEqual([{ value: "retail", label: "Retail" }]);
  });

  it("falls back to the slug as the label when the name is missing", () => {
    const out = mergeSeenIndustries([], [{ industry_slug: "misc" }]);
    expect(out).toEqual([{ value: "misc", label: "misc" }]);
  });
});
