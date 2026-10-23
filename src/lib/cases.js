export const CASE_STATUSES = { open: "Open", investigating: "Investigating", awaiting_reporter: "Waiting for your response", resolved: "Resolved", dismissed: "Dismissed" };
export const CASE_CATEGORIES = { unsafe_listing: "Unsafe listing", booking_dispute: "Booking dispute", forum_report: "Forum report", other: "Other concern" };
export const caseClosed = row => ["resolved", "dismissed"].includes(row.status);
export const caseTime = value => new Date(value).toLocaleString("en-BD", { dateStyle: "medium", timeStyle: "short" });
