// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../api", () => ({ createCase: vi.fn(), fetchCase: vi.fn(), fetchMyCases: vi.fn(), sendCaseMessage: vi.fn(), fetchAdminCases: vi.fn(), claimCase: vi.fn(), addCaseNote: vi.fn(), decideCase: vi.fn() }));
vi.mock("../auth/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("../auth/NavAuth", () => ({ default: () => <div>Account navigation</div> }));
import * as api from "../api";
import { useAuth } from "../auth/AuthContext";
import Reports from "../pages/Reports";
import AdminCases from "../components/AdminCases";

const row = { id: 17, title: "Please investigate a listing", description: "The address shown does not match the property I visited.", category: "unsafe_listing", status: "open", property_id: 4, property_title: "Room in Gulshan", reporter_name: "Rafi", reporter_id: 2, version: 1, created_at: "2026-10-24T10:00:00Z", updated_at: "2026-10-24T10:00:00Z", assigned_to: null, assigned_name: null, resolution: null, updates: [{ id: 1, kind: "opened", actor_name: "Rafi", body: "Report received", internal: false, created_at: "2026-10-24T10:00:00Z" }], allowed_statuses: ["investigating", "dismissed"] };
const mount = path => render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/my-reports" element={<Reports />} /><Route path="/reports/new" element={<Reports create />} /><Route path="/reports/:id" element={<Reports />} /><Route path="/admin" element={<AdminCases />} /></Routes></MemoryRouter>);

beforeEach(() => {
  useAuth.mockReturnValue({ user: { id: 2, name: "Rafi", role: "renter" }, ready: true, openAuth: vi.fn() });
  api.fetchMyCases.mockResolvedValue([row]); api.fetchCase.mockResolvedValue(row); api.fetchAdminCases.mockResolvedValue([row]);
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("submits a private report with the property supplied by the listing link", async () => {
  api.createCase.mockResolvedValue(row);
  mount("/reports/new?property_id=4");
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: row.title } });
  fireEvent.change(screen.getByLabelText("Details and evidence"), { target: { value: row.description } });
  fireEvent.click(screen.getByRole("button", { name: "Submit private report" }));
  await screen.findByRole("heading", { name: "Case #17" });
  expect(api.createCase).toHaveBeenCalledWith(expect.objectContaining({ category: "unsafe_listing", property_id: 4, booking_id: null, title: row.title }));
});

it("shows a reporter the resolution and removes the reply form for closed cases", async () => {
  api.fetchCase.mockResolvedValue({ ...row, status: "resolved", resolution: "We investigated and corrected the listing address." });
  mount("/reports/17");
  expect(await screen.findByText("We investigated and corrected the listing address.")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Send response" })).toBeNull();
});

it("submits additional information and refreshes the shared timeline", async () => {
  api.fetchCase.mockResolvedValue({ ...row, status: "awaiting_reporter" });
  api.sendCaseMessage.mockImplementation(async () => api.fetchCase.mockResolvedValue({ ...row, status: "investigating", updates: [...row.updates, { id: 2, kind: "message", actor_name: "Rafi", body: "I visited the property yesterday.", internal: false, created_at: row.created_at }] }));
  mount("/reports/17");
  fireEvent.change(await screen.findByLabelText("Your response"), { target: { value: "I visited the property yesterday." } });
  fireEvent.click(screen.getByRole("button", { name: "Send response" }));
  await screen.findByText("I visited the property yesterday.");
  expect(api.sendCaseMessage).toHaveBeenCalledWith("17", "I visited the property yesterday.");
});

it("requires login before fetching cases", () => {
  useAuth.mockReturnValue({ user: null, ready: true, openAuth: vi.fn() });
  mount("/my-reports");
  expect(screen.getByRole("button", { name: "Log in to manage reports" })).toBeTruthy();
  expect(api.fetchMyCases).not.toHaveBeenCalled();
});

it("keeps investigation notes private by default", async () => {
  useAuth.mockReturnValue({ user: { id: 3, name: "Admin", role: "admin" }, ready: true });
  api.addCaseNote.mockResolvedValue(row);
  mount("/admin?tab=cases&case=17");
  fireEvent.change(await screen.findByLabelText("Note or message"), { target: { value: "Check the owner's previous listings." } });
  expect(screen.getByLabelText("Admin-only investigation note").checked).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Add private note" }));
  await vi.waitFor(() => expect(api.addCaseNote).toHaveBeenCalledWith(17, "Check the owner's previous listings.", true));
});

it("records the chosen case status, public feedback and explicit listing hold", async () => {
  useAuth.mockReturnValue({ user: { id: 3, name: "Admin", role: "admin" }, ready: true });
  api.decideCase.mockResolvedValue(row);
  mount("/admin?tab=cases&case=17");
  fireEvent.change(await screen.findByLabelText("Update for reporter"), { target: { value: "We are investigating your listing report." } });
  fireEvent.click(screen.getByLabelText("Hold linked listing for admin review"));
  fireEvent.click(screen.getByRole("button", { name: "Save decision & share update" }));
  await vi.waitFor(() => expect(api.decideCase).toHaveBeenCalledWith(17, { expected_version: 1, status: "investigating", message: "We are investigating your listing report.", hold_listing: true }));
});

it("filters the admin queue and opens the matching investigation", async () => {
  useAuth.mockReturnValue({ user: { id: 3, name: "Admin", role: "admin" }, ready: true });
  mount("/admin?tab=cases");
  await screen.findByLabelText("New case status");
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "resolved" } });
  await vi.waitFor(() => expect(api.fetchAdminCases).toHaveBeenLastCalledWith(expect.objectContaining({ status: "resolved", skip: 0 })));
});
