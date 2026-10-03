import { describe, expect, it } from "vitest";
import { allowed, sameOrigin } from "./proxy-policy";
describe("employee proxy boundary", () => {
  it("forwards supported protected reads and approval mutations", () => {
    expect(allowed("workbench/cases", "GET")).toBe(true);
    expect(allowed("action-approvals/a-1/decision", "POST")).toBe(true);
    expect(allowed("reliability/cases/c-1/shadow", "POST")).toBe(true);
    expect(allowed("cases/c-1/memory/retrieve", "GET")).toBe(true);
  });
  it("refuses simulator, worker claims, traversal, unknown actions and methods", () => {
    for (const path of ["simulator/scenarios", "orchestration/worker/claim", "../workbench/cases", "cases/x/execute_payment", "http://example.org", "workbench/cases/../identity"]) expect(allowed(path, "POST")).toBe(false);
    expect(allowed("actions/submit", "DELETE")).toBe(false);
  });
  it("requires an exact browser origin for mutations", () => {
    expect(sameOrigin("http://127.0.0.1:3000", "http://127.0.0.1:3000/api/session")).toBe(true);
    expect(sameOrigin(null, "http://127.0.0.1:3000/api/session")).toBe(false);
    expect(sameOrigin("https://attacker.invalid", "http://127.0.0.1:3000/api/session")).toBe(false);
  });
});
