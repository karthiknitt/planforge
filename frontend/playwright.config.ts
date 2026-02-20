import { defineConfig, devices } from "@playwright/test";

/**
 * PlanForge Playwright E2E Configuration
 *
 * Two test projects:
 *   - "setup"       → one-time auth: signs up/in and saves cookies to auth.json
 *   - "chromium"    → all e2e tests; unauthenticated suite uses no storageState,
 *                     authenticated suite loads auth.json
 */

const BASE_URL = "http://localhost:3001";

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "./tests/e2e-results",
  fullyParallel: false, // auth setup must run first; keep serial for safety
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [["html", { outputFolder: "tests/playwright-report" }], ["list"]],

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    // 1. Auth setup — runs first, produces auth/user.json
    {
      name: "setup",
      testMatch: /.*\.setup\.ts/,
    },

    // 2. Authenticated tests — loads saved session
    {
      name: "authenticated",
      testMatch: /.*\.auth\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        storageState: "tests/e2e/auth/user.json",
      },
      dependencies: ["setup"],
    },

    // 3. Unauthenticated tests — no session
    {
      name: "unauthenticated",
      testMatch: /.*\.unauth\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
