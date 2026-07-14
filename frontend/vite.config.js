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
    //
    // `/static/rest_framework` is proxied too so the DRF browsable API's own
    // Bootstrap CSS/JS (served by Django) load when the page is viewed through
    // the Vite origin. NOTE: the match is scoped to `rest_framework/` on
    // purpose — the React app imports its own theme at `/static/css/theme.css`,
    // which Vite must serve as a JS module. A broad `/static` proxy would send
    // that request to Django and return raw CSS, breaking the app on boot.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/static/rest_framework": {
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
