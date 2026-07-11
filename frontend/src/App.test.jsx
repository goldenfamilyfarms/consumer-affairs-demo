import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App.jsx";

// Smoke test: confirms the Vitest + React Testing Library + JSX toolchain is
// wired up correctly and the app shell renders.
describe("App", () => {
  it("renders the page heading", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /brand reviews/i })).toBeInTheDocument();
  });
});
