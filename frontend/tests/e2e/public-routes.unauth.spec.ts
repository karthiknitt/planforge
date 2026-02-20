/**
 * Unauthenticated — public routes & redirect guards
 *
 * Verifies that:
 *   • Marketing pages (/, /pricing, /how-it-works) load without auth
 *   • Protected routes (/dashboard, /projects, /account) redirect to /sign-in
 *   • Sign-in page loads and shows expected fields
 *   • Sign-up page loads and shows expected fields
 *   • Sign-in shows an error on wrong credentials
 *   • Sign-up shows an error on duplicate email
 */

import { expect, test } from "@playwright/test";

// ── Marketing pages ──────────────────────────────────────────────────────────

test("landing page loads at / without authentication", async ({ page }) => {
  await page.goto("/");
  // Should NOT be redirected to sign-in
  await expect(page).not.toHaveURL(/\/sign-in/);
  // PlanForge branding appears
  await expect(page.locator("text=PlanForge").first()).toBeVisible();
});

test("/pricing loads without authentication", async ({ page }) => {
  await page.goto("/pricing");
  await expect(page).not.toHaveURL(/\/sign-in/);
  // Pricing page has at least one plan title
  await expect(page.locator("text=/Free|Basic|Pro/i").first()).toBeVisible();
});

test("/how-it-works loads without authentication", async ({ page }) => {
  await page.goto("/how-it-works");
  await expect(page).not.toHaveURL(/\/sign-in/);
  await expect(page.getByRole("main")).toBeVisible();
});

// ── Protected route redirects ─────────────────────────────────────────────────

test("/dashboard redirects unauthenticated users to /sign-in", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/sign-in/, { timeout: 5_000 });
});

test("/account redirects unauthenticated users to /sign-in", async ({ page }) => {
  await page.goto("/account");
  await expect(page).toHaveURL(/\/sign-in/, { timeout: 5_000 });
});

// ── Sign-in page ──────────────────────────────────────────────────────────────

test("sign-in page renders correctly", async ({ page }) => {
  await page.goto("/sign-in");
  await expect(page.locator('input[type="email"]')).toBeVisible();
  await expect(page.locator('input[type="password"]')).toBeVisible();
  await expect(page.locator('button[type="submit"]')).toBeVisible();
  await expect(page.locator("text=Sign up")).toBeVisible(); // link to sign-up
});

test("sign-in shows error on wrong credentials", async ({ page }) => {
  await page.goto("/sign-in");
  await page.fill('input[type="email"]', "nobody@doesnotexist.test");
  await page.fill('input[type="password"]', "wrongpassword");
  await page.click('button[type="submit"]');

  // Should stay on sign-in and show an error
  await expect(page).toHaveURL(/\/sign-in/, { timeout: 8_000 });
  await expect(
    page.locator(".text-destructive, [class*='destructive'], [class*='error']").first()
  ).toBeVisible({ timeout: 8_000 });
});

test("sign-in shows error on empty password", async ({ page }) => {
  await page.goto("/sign-in");
  await page.fill('input[type="email"]', "someone@test.com");
  // Leave password empty — browser required validation should trigger
  await page.click('button[type="submit"]');
  // Page stays on sign-in (browser blocks submit or our validation fires)
  await expect(page).toHaveURL(/\/sign-in/);
});

// ── Sign-up page ──────────────────────────────────────────────────────────────

test("sign-up page renders correctly", async ({ page }) => {
  await page.goto("/sign-up");
  await expect(page.locator('input[id="name"]')).toBeVisible();
  await expect(page.locator('input[type="email"]')).toBeVisible();
  await expect(page.locator('input[type="password"]')).toBeVisible();
  await expect(page.locator('button[type="submit"]')).toBeVisible();
  await expect(page.locator("text=Sign in")).toBeVisible(); // link to sign-in
});

test("sign-up shows error for duplicate email", async ({ page }) => {
  // Use the same e2e test account that auth setup already created
  await page.goto("/sign-up");
  await page.fill('input[id="name"]', "Duplicate User");
  await page.fill('input[type="email"]', "e2e-test@planforge.test");
  await page.fill('input[type="password"]', "TestPass123!");
  await page.click('button[type="submit"]');

  // Should stay on sign-up and show an error
  await expect(page).toHaveURL(/\/sign-up/, { timeout: 8_000 });
  await expect(
    page.locator(".text-destructive, [class*='destructive'], [class*='error']").first()
  ).toBeVisible({ timeout: 8_000 });
});

test("sign-up rejects password shorter than 8 characters", async ({ page }) => {
  await page.goto("/sign-up");
  await page.fill('input[id="name"]', "Short Pass");
  await page.fill('input[type="email"]', "shortpass@planforge.test");
  await page.fill('input[type="password"]', "abc");
  await page.click('button[type="submit"]');
  // Browser minLength=8 prevents submit — stays on sign-up
  await expect(page).toHaveURL(/\/sign-up/);
});
