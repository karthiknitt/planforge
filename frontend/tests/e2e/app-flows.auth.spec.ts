/**
 * Authenticated — app flows (dashboard, projects, account, sign-out)
 *
 * Loaded with a pre-authenticated session from auth/user.json (created by auth.setup.ts).
 * Tests run with a logged-in user, so:
 *   • Protected routes are accessible
 *   • Auth pages redirect away to /dashboard
 *   • Core app interactions work end-to-end
 */

import { expect, test } from "@playwright/test";

// ── Auth redirect for authenticated users ─────────────────────────────────────

test("authenticated user visiting /sign-in is redirected to /dashboard", async ({ page }) => {
  await page.goto("/sign-in");
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 5_000 });
});

test("authenticated user visiting /sign-up is redirected to /dashboard", async ({ page }) => {
  await page.goto("/sign-up");
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 5_000 });
});

// ── Dashboard ─────────────────────────────────────────────────────────────────

test("dashboard loads and shows PlanForge header", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.locator("text=PlanForge").first()).toBeVisible();
});

test("dashboard shows user email or account link in header", async ({ page }) => {
  await page.goto("/dashboard");
  // Either the email is visible or a link to /account
  const hasEmail = await page.locator("text=e2e-test@planforge.test").isVisible();
  const hasAccount = await page.locator('[href="/account"]').isVisible();
  expect(hasEmail || hasAccount).toBe(true);
});

test("dashboard shows new project button", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(
    page.locator("a[href='/projects/new'], button:has-text('New'), a:has-text('New')").first()
  ).toBeVisible({ timeout: 5_000 });
});

// ── Account page ──────────────────────────────────────────────────────────────

test("account page loads with plan info", async ({ page }) => {
  await page.goto("/account");
  await expect(page).toHaveURL(/\/account/);
  // Should show plan tier badge (Free / Basic / Pro)
  await expect(page.locator("text=/Free|Basic|Pro/i").first()).toBeVisible({ timeout: 5_000 });
});

// ── New project flow ──────────────────────────────────────────────────────────

test("new project page loads with form fields", async ({ page }) => {
  await page.goto("/projects/new");
  await expect(page).toHaveURL(/\/projects\/new/);
  // Plot dimension inputs should be visible
  await expect(page.locator("input").first()).toBeVisible({ timeout: 5_000 });
});

test("new project form: submit with valid data navigates to project", async ({ page }) => {
  await page.goto("/projects/new");
  await expect(page).toHaveURL(/\/projects\/new/);

  // Fill in a minimal valid project — field names as rendered in the form
  // Project name
  const nameInput = page.locator('input[id="name"], input[placeholder*="project" i]').first();
  if (await nameInput.isVisible()) {
    await nameInput.fill("E2E Test House");
  }

  // Plot width (metres)
  const widthInput = page
    .locator('input[id*="width" i], input[id*="plotWidth" i], input[placeholder*="width" i]')
    .first();
  if (await widthInput.isVisible()) await widthInput.fill("10");

  // Plot length / depth
  const lengthInput = page
    .locator('input[id*="length" i], input[id*="depth" i], input[placeholder*="length" i]')
    .first();
  if (await lengthInput.isVisible()) await lengthInput.fill("15");

  // Submit
  const submitBtn = page.locator('button[type="submit"]').first();
  await submitBtn.click();

  // After submit, should land on /projects/<id> or show a layout
  await expect(page).not.toHaveURL(/\/projects\/new/, { timeout: 15_000 });
});

// ── Sign-out ──────────────────────────────────────────────────────────────────

test("sign-out logs user out and redirects away from dashboard", async ({ page }) => {
  await page.goto("/dashboard");
  // Click the sign-out button (text may vary: "Sign out", "Logout")
  const signOutBtn = page
    .locator('button:has-text("Sign out"), button:has-text("Logout"), button:has-text("Sign Out")')
    .first();
  await expect(signOutBtn).toBeVisible({ timeout: 5_000 });
  await signOutBtn.click();

  // After sign-out: should be on landing page or sign-in, NOT dashboard
  await expect(page).not.toHaveURL(/\/dashboard/, { timeout: 8_000 });
});

// ── Pricing page ──────────────────────────────────────────────────────────────

test("authenticated user can visit /pricing (public marketing page)", async ({ page }) => {
  await page.goto("/pricing");
  // Marketing page is still accessible when logged in
  await expect(page).not.toHaveURL(/\/sign-in/);
  await expect(page.locator("text=/Free|Basic|Pro/i").first()).toBeVisible();
});
