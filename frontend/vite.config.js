import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite + React 18 dev/build config. Vitest config is colocated here so the
// test runner shares the same module resolution and JSX transform.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy API calls to the Django backend during local development so the
    // frontend can call the same-origin relative path `/api/brands/`.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
    css: false,
  },
});
