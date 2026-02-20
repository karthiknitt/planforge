/**
 * Auth Setup — runs once before all authenticated test suites.
 *
 * Attempts to sign in with the test account. If the account doesn't exist yet
 * (first run), it signs up first, then saves the session cookies to
 * tests/e2e/auth/user.json so every authenticated test project can reuse them.
 */

import path from "node:path";
import { expect, test as setup } from "@playwright/test";

const STORAGE_STATE = path.join(__dirname, "auth/user.json");
const TEST_EMAIL = "e2e-test@planforge.test";
const TEST_PASSWORD = "TestPass123!";
const TEST_NAME = "E2E Test User";

setup("authenticate test user", async ({ page }) => {
  // Try sign-in first; fall back to sign-up on error
  await page.goto("/sign-in");
  await page.fill('input[type="email"]', TEST_EMAIL);
  await page.fill('input[type="password"]', TEST_PASSWORD);
  await page.click('button[type="submit"]');

  // Wait briefly to see if sign-in succeeds
  await page.waitForTimeout(1500);

  const isOnDashboard = page.url().includes("/dashboard");

  if (!isOnDashboard) {
    // Account doesn't exist — sign up
    await page.goto("/sign-up");
    await page.fill('input[id="name"]', TEST_NAME);
    await page.fill('input[type="email"]', TEST_EMAIL);
    await page.fill('input[type="password"]', TEST_PASSWORD);
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });
  }

  // Save session cookies for reuse in all authenticated tests
  await page.context().storageState({ path: STORAGE_STATE });
});
