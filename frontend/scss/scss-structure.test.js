// scss-structure.test.js — structural-equivalence test for the SCSS source tree.
//
// Compiles `main.scss` with Dart Sass and asserts the emitted CSS preserves the
// reference theme's structure: the `:root` design tokens, the core component
// rules (`.grid`, `.card`, `.stars`, `.badge`), and the responsive
// `@media (max-width: 640px)` breakpoint.
//
// Validates: Requirements 13.2, 13.4

import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, it, expect, beforeAll } from "vitest";
import * as sass from "sass";

const here = dirname(fileURLToPath(import.meta.url));
const entry = resolve(here, "main.scss");

describe("SCSS structural equivalence with reference theme", () => {
  let css;

  beforeAll(() => {
    // `compile` resolves `@use` partials relative to the entry file, so the
    // whole source tree is exercised through a single call.
    css = sass.compile(entry).css;
  });

  it("compiles main.scss to non-empty CSS", () => {
    expect(typeof css).toBe("string");
    expect(css.length).toBeGreaterThan(0);
  });

  it("emits the :root design tokens (Requirement 13.2)", () => {
    expect(css).toContain(":root");

    // Reference tokens: colors, radius, shadows, max width, and font family.
    const tokens = [
      "--color-bg:",
      "--color-card:",
      "--color-text:",
      "--color-muted:",
      "--color-border:",
      "--color-primary:",
      "--color-primary-dark:",
      "--color-accent:",
      "--color-star:",
      "--color-star-empty:",
      "--radius:",
      "--shadow-sm:",
      "--shadow:",
      "--max-width:",
      "--font-sans:",
    ];
    for (const token of tokens) {
      expect(css, `expected compiled CSS to declare ${token}`).toContain(token);
    }
  });

  it("carries through representative token values", () => {
    expect(css).toContain("--color-primary: #0f766e");
    expect(css).toContain("--radius: 10px");
    expect(css).toContain("--max-width: 1100px");
    expect(css).toContain("--font-sans:");
    // The font stack should start with the system UI font.
    expect(css).toMatch(/--font-sans:\s*-apple-system/);
  });

  it("emits the core component rules (Requirement 13.4)", () => {
    for (const selector of [".grid", ".card", ".stars", ".badge"]) {
      expect(
        css,
        `expected compiled CSS to contain the ${selector} rule`
      ).toMatch(new RegExp(`\\${selector}\\b`));
    }

    // The responsive card grid is the reference layout's defining structure.
    expect(css).toContain("grid-template-columns");
  });

  it("preserves the responsive breakpoint (Requirement 13.4)", () => {
    expect(css).toContain("@media (max-width: 640px)");

    // At the mobile breakpoint the grid collapses to a single column.
    const mobileBlock = css.slice(css.indexOf("@media (max-width: 640px)"));
    expect(mobileBlock).toContain("grid-template-columns: 1fr");
  });
});
