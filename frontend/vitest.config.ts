import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
export default defineConfig({plugins: [react()], resolve: {alias: {"@": fileURLToPath(new URL("./src", import.meta.url))}},
  test: {environment: "jsdom", include: ["src/**/*.test.ts", "src/**/*.test.tsx"], setupFiles: ["./src/test-setup.ts"], reporters: ["default", "junit"], outputFile: {junit: "../phase15-frontend-unit-results.xml"}}});
