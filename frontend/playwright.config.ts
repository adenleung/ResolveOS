import { defineConfig } from "@playwright/test";
export default defineConfig({testDir: "./e2e", timeout: 60000, expect: {timeout: 15000}, workers: 1, fullyParallel: false,
  reporter: [["list"], ["junit", {outputFile: "../phase15-browser-results.xml"}]],
  use: {baseURL: "http://127.0.0.1:3000", channel: "msedge", headless: true, viewport: {width: 1440, height: 1000},
    trace: "off", video: "off", screenshot: "only-on-failure"},
});
