import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API's routes, proxied in development so the browser stays same-origin (no CORS
// change; spec 5.0). The deployed site is same-origin too (Phase 7).
const API = "http://127.0.0.1:8000";
const API_ROUTES = ["/plants", "/runs", "/budget", "/demo"];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(API_ROUTES.map((route) => [route, API])),
    // tests read the contract fixtures from ../contract
    fs: { allow: [".."] },
  },
  test: {
    environment: "jsdom",
    restoreMocks: true,
    setupFiles: ["src/test/setup.ts"],
  },
});
