// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../api", () => ({
  confirmAction: vi.fn(async (id) => ({ id, status: "confirmed", booking: { id: 77 } })),
  cancelAction: vi.fn(async (id) => ({ id, status: "cancelled" })),
  getComments: vi.fn(), getForumPost: vi.fn(), streamAgent: vi.fn(),
}));
const auth = { user: { name: "Nusrat", phone: "01700000001", role: "renter" }, openAuth: vi.fn() };
vi.mock("../auth/AuthContext", () => ({ useAuth: () => auth }));

import { cancelAction, confirmAction } from "../api";
import { PendingActionCard } from "../components/AIAssistant";

const action = {
  id: 5, type: "create_booking",
  summary: { title: "Women-only 2-bed flat", check_in: "2027-01-01", check_out: "2027-03-02",
             rental_type: "monthly", unit_price: 22000, total_price: 44000 },
};

function renderCard(onChange = vi.fn()) {
  render(<MemoryRouter><PendingActionCard action={action} onChange={onChange} /></MemoryRouter>);
  return onChange;
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("PendingActionCard", () => {
  it("shows the draft and books nothing until the user clicks Confirm", async () => {
    const onChange = renderCard();
    expect(screen.getByText("Women-only 2-bed flat")).toBeTruthy();
    expect(screen.getByText("৳44,000")).toBeTruthy();
    expect(confirmAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Confirm booking"));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ status: "confirmed" })));
    expect(confirmAction).toHaveBeenCalledWith(5, {});
  });

  it("cancel never calls confirm", async () => {
    const onChange = renderCard();
    fireEvent.click(screen.getByText("Cancel"));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ status: "cancelled" })));
    expect(cancelAction).toHaveBeenCalledWith(5);
    expect(confirmAction).not.toHaveBeenCalled();
  });

  it("asks logged-out users to log in instead of confirming", () => {
    const saved = auth.user;
    auth.user = null;
    renderCard();
    fireEvent.click(screen.getByText("Log in to confirm"));
    expect(auth.openAuth).toHaveBeenCalled();
    expect(confirmAction).not.toHaveBeenCalled();
    auth.user = saved;
  });
});
