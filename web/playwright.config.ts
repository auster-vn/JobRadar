import {defineConfig, devices} from "playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop-chromium",
      use: {...devices["Desktop Chrome"]},
      testIgnore: /responsive\.spec\.ts/,
    },
    {
      name: "mobile-chromium",
      use: {...devices["Pixel 7"]},
      testMatch: /responsive\.spec\.ts/,
    },
  ],
});
