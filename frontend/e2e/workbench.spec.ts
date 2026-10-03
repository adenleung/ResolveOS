import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync, mkdirSync } from "node:fs";
const configuration = readFileSync("../.env.demo", "utf8").split(/\r?\n/);
const manifest = JSON.parse(readFileSync("../demo-manifest.local.json", "utf8")) as {journeys: Record<string, {case_id: string; stale_authorization_id?: string}>};
const origin = "http://127.0.0.1:3000";
function credential(role: "WORKER" | "REVIEWER"): string { const name = `ORCHESTRATION_DEV_${role}_TOKEN=`; const line = configuration.find(line => line.startsWith(name)); if (!line) throw new Error("Isolated demo credentials are not configured"); return line.slice(name.length); }
async function login(page: Page, role: "WORKER" | "REVIEWER" = "REVIEWER") {
  await page.goto("/"); await page.getByLabel("Authorized development token").fill(credential(role));
  await page.getByRole("button", {name: "Connect to ResolveOS"}).click();
  await expect(page.getByRole("heading", {name: "Operations overview"})).toBeVisible();
  await expect(page.getByRole("link", {name: "View all cases"})).toBeVisible();
}
test("real overview, accessible navigation and protected session", async ({page}) => {
  await login(page);
  await expect(page.getByText("Verified resolutions", {exact: true})).toBeVisible();
  await expect(page.getByText("Missing confirmation after settled payment and posted ledger")).toBeVisible();
  const cookie = (await page.context().cookies()).find(cookie => cookie.name === "resolveos_session");
  expect(cookie?.httpOnly).toBe(true); expect(cookie?.sameSite).toBe("Strict");
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  const accessibility = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(accessibility.violations).toEqual([]);
  mkdirSync("../screenshots", {recursive: true});
  await page.screenshot({path: "../screenshots/phase15-overview.png", fullPage: true});
});
test("actual case filtering, source inspection and independently verified outcome", async ({page}) => {
  await login(page); await page.goto("/cases");
  await page.getByLabel("Filter cases").fill("not-a-real-case"); await page.getByRole("button", {name: "Apply filters"}).click();
  await expect(page.getByText("No cases match these filters.")).toBeVisible();
  await page.goto(`/cases/${manifest.journeys.A.case_id}`);
  await expect(page.getByText("RESOLVED", {exact: true})).toBeVisible();
  await page.getByRole("tab", {name: "Evidence", exact: true}).click();
  await page.getByText("Inspect observed fields and provenance", {exact: true}).first().click();
  await expect(page.locator("pre").first()).toContainText("source_system");
  await page.getByRole("tab", {name: "Controls", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Actual execution and independent verification"})).toBeVisible();
  await page.getByText("Inspect source record", {exact: true}).last().click();
  await expect(page.locator("pre").last()).toContainText("VERIFIED");
  await expect(page.getByRole("button", {name: "Submit synthetic confirmation replay"})).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({path: "../screenshots/phase15-case.png", fullPage: true});
});
test("human handover assignment persists and has attributed history", async ({page}) => {
  await login(page); await page.goto("/approvals");
  await expect(page.getByRole("heading", {name: "Workflow handovers"})).toBeVisible();
  const assign = page.getByRole("button", {name: "Assign review to me"});
  if (await assign.isEnabled()) await assign.click();
  await expect(assign).toBeDisabled();
  await page.getByRole("button", {name: "Load review history"}).last().click();
  await page.getByText("Inspect actors, reasons and review transitions").click();
  await expect(page.locator("pre").last()).toContainText("development-reviewer");
  await expect(page.locator("pre").last()).toContainText("ASSIGN");
});
test("shadow and recorded replay separate hypothesis from independent outcome", async ({page}) => {
  await login(page); await page.goto(`/shadow?case=${manifest.journeys.A.case_id}`);
  await expect(page.getByText("SHADOW · NOT EVALUATED FOR AUTHORIZATION · EXECUTION PERMITTED: FALSE")).toBeVisible();
  await expect(page.getByText("INDEPENDENTLY VERIFIED RESOLUTION", {exact: true})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Recorded workflow timeline"})).toBeVisible();
  await expect(page.getByText("Independent verification", {exact: true})).toBeVisible();
  await expect(page.getByText("HYPOTHETICAL", {exact: true}).first()).toBeVisible();
});
test("reviewed history and honest offline Model Lab", async ({page}) => {
  await login(page); await page.goto("/memory");
  await expect(page.getByText("Valid reviewed history", {exact: true})).toBeVisible();
  await page.goto("/models");
  await expect(page.getByText("OFFLINE EXPERIMENTAL EVALUATION · NO OPERATIONAL MODEL ENABLED")).toBeVisible();
  await expect(page.getByRole("cell", {name: "Not evaluated", exact: true}).first()).toBeVisible();
  await expect(page.getByText("BLOCKED DATASET", {exact: true}).first()).toBeVisible();
});
test("worker cannot review approvals and the proxy rejects foreign-origin mutations", async ({page}) => {
  await login(page, "WORKER"); await page.goto("/approvals");
  await expect(page.getByRole("alert").filter({hasText: "Reviewer role required"})).toBeVisible();
  expect((await page.request.get("/api/backend/workbench/approvals")).status()).toBe(403);
  expect((await page.request.post("/api/backend/actions/submit", {headers: {Origin: "https://attacker.invalid"}, data: {authorization_id: "invalid"}})).status()).toBe(403);
  expect((await page.request.post("/api/backend/simulator/scenarios", {headers: {Origin: origin}, data: {}})).status()).toBe(404);
});
test("unsafe approved action remains blocked after the policy changes", async ({page}) => {
  await login(page, "WORKER"); await page.goto(`/cases/${manifest.journeys.C.case_id}`);
  await page.getByRole("tab", {name: "Controls", exact: true}).click();
  await expect(page.getByText("BLOCKED", {exact: true})).toBeVisible();
  const submit = page.getByRole("button", {name: "Submit synthetic confirmation replay"});
  for (const button of await submit.all()) await expect(button).toBeDisabled();
  const response = await page.request.post("/api/backend/actions/submit", {headers: {Origin: origin}, data: {authorization_id: manifest.journeys.C.stale_authorization_id}});
  expect(response.status()).toBe(409);
  expect((await page.request.get(`/api/backend/cases/${manifest.journeys.C.case_id}/actions`)).ok()).toBe(true);
  expect(await (await page.request.get(`/api/backend/cases/${manifest.journeys.C.case_id}/actions`)).json()).toEqual([]);
});
test("failed backend request remains an explicit failure with no invented metrics", async ({page}) => {
  await login(page); await page.route("**/api/backend/intelligence/report", route => route.fulfill({status: 503, contentType: "application/json", body: JSON.stringify({detail: "Controlled test: backend unavailable"})}));
  await page.getByRole("button", {name: "Refresh", exact: true}).click();
  await expect(page.getByRole("alert").filter({hasText: "Controlled test: backend unavailable"})).toBeVisible();
  await expect(page.getByText("Verified resolutions", {exact: true})).toHaveCount(0);
});
test("mobile case centre retains accessible navigation and real records", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844}); await login(page);
  await page.getByRole("button", {name: "Toggle navigation"}).click();
  await page.getByRole("navigation", {name: "Main navigation"}).getByRole("link", {name: "Cases", exact: true}).click();
  await expect(page.getByText("Missing confirmation after settled payment and posted ledger")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Missing confirmation after settled payment and posted ledger")).toBeVisible();
  await page.screenshot({path: "../screenshots/phase15-mobile.png", fullPage: true});
});
