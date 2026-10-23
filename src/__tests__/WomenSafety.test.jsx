// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../api", () => ({ fetchWomenSafety: vi.fn(), submitWomenSafety: vi.fn(), decideWomenSafety: vi.fn(), fetchWomenSafetyQueue: vi.fn(), downloadPrivateDocument: vi.fn() }));
vi.mock("../auth/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("../components/OwnerPhotos", () => ({ photoUrl: u => u }));
import * as api from "../api";
import { useAuth } from "../auth/AuthContext";
import WomenSafetyPanel, { AdminWomenSafety } from "../components/WomenSafetyPanel";

const row = { property_id: 4, owner_id: 2, title: "Women-only apartment", owner_name: "Karim", address: "House 12, Road 3", area: "Dhanmondi", description: "A private women-only apartment.", is_female_only: true, status: "not_submitted", version: 3, document_check_status: "reviewed", listing_status: "pending", submission: {}, photos: [], documents: [], history: [] };
const mount = element => render(<MemoryRouter>{element}</MemoryRouter>);
beforeEach(() => {
  useAuth.mockReturnValue({ user: { id: 2, role: "owner" } });
  api.fetchWomenSafety.mockResolvedValue({ ...row });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("requires owner confirmations and sends a separate versioned review request", async () => {
  api.submitWomenSafety.mockResolvedValue({});
  mount(<WomenSafetyPanel propertyId={4} />);
  const button = await screen.findByRole("button", { name: "Request safety review" });
  expect(button.disabled).toBe(true);
  for (const check of screen.getAllByRole("checkbox")) fireEvent.click(check);
  const notes = "Working locks, common lighting, privacy and emergency contact details are available for review.";
  fireEvent.change(screen.getByRole("textbox"), { target: { value: notes } });
  fireEvent.click(button);
  await vi.waitFor(() => expect(api.submitWomenSafety).toHaveBeenCalledWith(4, expect.objectContaining({ expected_version: 3, notes })));
});

it("shows admin feedback and leaves pending requests waiting for review", async () => {
  api.fetchWomenSafety.mockResolvedValue({ ...row, status: "pending", feedback: "Please provide photos of the entrance lighting." });
  mount(<WomenSafetyPanel propertyId={4} />);
  expect(await screen.findByText("Please provide photos of the entrance lighting.")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Request safety review" })).toBeNull();
});

it("does not allow safety approval until separate ownership checks pass", async () => {
  useAuth.mockReturnValue({ user: { id: 3, role: "admin" } });
  api.fetchWomenSafety.mockResolvedValue({ ...row, status: "pending", document_check_status: "needs_review" });
  mount(<WomenSafetyPanel propertyId={4} admin />);
  const button = await screen.findByRole("button", { name: "Approve safety review" });
  for (const check of screen.getAllByRole("checkbox")) fireEvent.click(check);
  expect(button.disabled).toBe(true);
});

it("records the admin checklist and evidence notes as an independent decision", async () => {
  useAuth.mockReturnValue({ user: { id: 3, role: "admin" } });
  api.fetchWomenSafety.mockResolvedValue({ ...row, status: "pending" });
  api.decideWomenSafety.mockResolvedValue({});
  mount(<WomenSafetyPanel propertyId={4} admin />);
  const button = await screen.findByRole("button", { name: "Approve safety review" });
  for (const check of screen.getAllByRole("checkbox")) fireEvent.click(check);
  const notes = "Reviewed documents and photo evidence with the owner and checked the emergency contact arrangements.";
  fireEvent.change(screen.getByRole("textbox"), { target: { value: notes } });
  fireEvent.click(button);
  await vi.waitFor(() => expect(api.decideWomenSafety).toHaveBeenCalledWith(4, expect.objectContaining({ expected_version: 3, verdict: "approved", notes, checklist: expect.objectContaining({ evidence_reviewed: true }) })));
});

it("filters the separate admin safety queue", async () => {
  useAuth.mockReturnValue({ user: { id: 3, role: "admin" } });
  api.fetchWomenSafetyQueue.mockResolvedValue({ items: [], total: 0 });
  mount(<AdminWomenSafety />);
  await screen.findByText("No listings in this safety review queue.");
  fireEvent.change(screen.getByLabelText("Safety review status"), { target: { value: "approved" } });
  await vi.waitFor(() => expect(api.fetchWomenSafetyQueue).toHaveBeenLastCalledWith({ status: "approved", skip: 0, limit: 20 }));
});
