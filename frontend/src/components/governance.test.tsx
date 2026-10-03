import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReviewForm, PermissionDenied } from "./governance";
import { Badge, Empty } from "./ui";
describe("review authority and state", () => {
  it("requires a reason and submits only the declared action-bound operation", async () => {
    const mutate = vi.fn().mockResolvedValue(true);
    render(<ReviewForm operations={["APPROVE", "REJECT"]} path="action-approvals/a/decision" bodyKey="operation" busy={false} mutate={mutate} />);
    expect(screen.getByRole("button", {name: "Record review decision"})).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Decision reason"), {target: {value: " Current source checked "}});
    fireEvent.click(screen.getByRole("button", {name: "Record review decision"}));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith("action-approvals/a/decision", {operation: "APPROVE", reason: "Current source checked"}));
  });
  it("keeps workflow handover distinct from action approval", async () => {
    const mutate = vi.fn().mockResolvedValue(false);
    render(<ReviewForm operations={["REQUEST_MORE_INVESTIGATION"]} path="reviews/r/decision" bodyKey="decision" busy={false} mutate={mutate} />);
    fireEvent.change(screen.getByLabelText("Decision reason"), {target: {value: "Conflicting observations"}});
    fireEvent.click(screen.getByRole("button", {name: "Record review decision"}));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith("reviews/r/decision", {decision: "REQUEST_MORE_INVESTIGATION", reason: "Conflicting observations"}));
    expect(screen.getByLabelText("Decision reason")).toHaveValue("Conflicting observations");
  });
  it("requires a corrected summary for governed memory correction", () => {
    render(<ReviewForm operations={["CORRECT"]} path="memory/versions/v/review" bodyKey="operation" busy={false} mutate={vi.fn()} memory />);
    fireEvent.change(screen.getByLabelText("Decision reason"), {target: {value: "Correct historical wording"}});
    expect(screen.getByRole("button", {name: "Record review decision"})).toBeDisabled();
  });
  it("renders explicit denied and empty states", () => {
    render(<><PermissionDenied /><Empty>No evidence returned.</Empty></>);
    expect(screen.getByRole("alert")).toHaveTextContent("Reviewer role required");
    expect(screen.getByText("No evidence returned.")).toBeVisible();
  });
  it("never styles an unverified result as verified success", () => {
    render(<Badge value="NO INDEPENDENTLY VERIFIED RESOLUTION" />);
    expect(screen.getByText("NO INDEPENDENTLY VERIFIED RESOLUTION")).toHaveClass("blue");
  });
});
