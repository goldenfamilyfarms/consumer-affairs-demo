// Vitest global setup: extends `expect` with jest-dom matchers and clears the
// DOM between tests so React Testing Library renders start clean.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
