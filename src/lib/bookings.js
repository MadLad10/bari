export function bookingState(booking, now = new Date()) {
  if (booking.status === "cancelled") return booking.cancellation_reason === "owner_declined" ? "rejected" : "cancelled";
  if (new Date(booking.check_out) <= now) return booking.status === "confirmed" ? "completed" : "expired";
  return booking.status;
}

export const BOOKING_LABELS = {
  pending: "Awaiting owner", confirmed: "Confirmed", cancelled: "Cancelled", rejected: "Rejected by owner",
  completed: "Completed", expired: "Request expired",
};

export function canCancelBooking(booking, now = new Date()) {
  return ["pending", "confirmed"].includes(booking.status) && new Date(booking.check_out) > now;
}

export function cancellationDescription(booking) {
  return {
    owner_declined: "The owner rejected this booking request. The reserved dates have been released.",
    renter_cancelled: "You cancelled this booking. The reserved dates have been released.",
    owner_cancelled: "The property owner cancelled this booking. The reserved dates have been released.",
    admin_cancelled: "An admin cancelled this booking. The reserved dates have been released.",
  }[booking.cancellation_reason] || "This booking was cancelled. The reserved dates have been released.";
}

export const bookingMoney = value => `৳${Number(value).toLocaleString("en-BD", { maximumFractionDigits: 2 })}`;
export const bookingDate = value => new Date(value).toLocaleString("en-BD", { dateStyle: "medium", timeStyle: "short" });
