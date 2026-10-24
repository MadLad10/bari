import { streamSSE } from "./lib/sse";

// Production (Vercel) serves the API from the same origin under /api; local dev talks to the Docker backend.
export const API_ROOT = import.meta.env.VITE_API_ROOT ?? (import.meta.env.PROD ? "" : "http://localhost:8001");
const BASE = `${API_ROOT}/api`;
const TOKEN_KEY = "bari_token";

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage unavailable */ }
}

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function errorMessage(detail, fallback) {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  return JSON.stringify(detail);
}

async function request(path, { method = "GET", body, form, fallback = "Request failed" } = {}) {
  const headers = { ...authHeaders() };
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${path}`, { method, headers, body: payload });
  if (res.status === 401 && getToken()) {
    setToken(null);
    window.dispatchEvent(new Event("bari:logout"));
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const e = new Error(errorMessage(err.detail, fallback));
    e.status = res.status;
    throw e;
  }
  return res.status === 204 ? null : res.json();
}

function qs(params = {}) {
  const s = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined)
  ).toString();
  return s ? `?${s}` : "";
}

// Auth
export const signup = (data) => request("/auth/signup", { method: "POST", body: data, fallback: "Signup failed" });
export const login = (email, password) =>
  request("/auth/login", { method: "POST", body: { email, password }, fallback: "Login failed" });
export const fetchMe = () => request("/auth/me");

// Properties
export const fetchProperties = (params = {}) => request(`/properties/${qs(params)}`, { fallback: "Failed to fetch properties" });
export const countProperties = (params = {}) => request(`/properties/count${qs(params)}`);
export const fetchPropertyMap = (params = {}) => request(`/properties/map${qs(params)}`);
export const fetchNearby = id => request(`/properties/${id}/nearby`);
export const fetchRoute = (id, destinationId) => request(`/properties/${id}/route`, { method: "POST", body: { destination_id: destinationId } });
export const fetchProperty = (id) => request(`/properties/${id}`, { fallback: "Property not found" });
export const createProperty = (data) => request("/properties/", { method: "POST", body: data });

export function uploadPhoto(propertyId, file) {
  const form = new FormData();
  form.append("file", file);
  return request(`/properties/${propertyId}/photos`, { method: "POST", form, fallback: "Upload failed" });
}

export function uploadDocument(propertyId, file) {
  const form = new FormData();
  form.append("file", file);
  return request(`/properties/${propertyId}/documents`, { method: "POST", form, fallback: "Upload failed" });
}

// Bookings
export const getAvailability = (propertyId) =>
  request(`/bookings/property/${propertyId}/availability`, { fallback: "Failed to fetch availability" });
export const createBooking = (data) => request("/bookings/", { method: "POST", body: data, fallback: "Booking failed" });
export const quoteBooking = (data) => request("/bookings/quote", { method: "POST", body: data, fallback: "Could not calculate this booking" });
export const fetchMyBookings = () => request("/bookings/mine");
export const fetchBooking = (id) => request(`/bookings/${id}`, { fallback: "Booking not found or unavailable" });
export const fetchOwnerBookings = () => request("/bookings/owner");
export const acceptBooking = (id) => request(`/bookings/${id}/accept`, { method: "PATCH" });
export const declineBooking = (id) => request(`/bookings/${id}/decline`, { method: "PATCH" });
export const cancelBooking = (id) => request(`/bookings/${id}/cancel`, { method: "PATCH" });

// Owner–renter chat
export const getChatMessages = (propertyId, sessionToken) =>
  request(`/chat/${propertyId}/${sessionToken}`, { fallback: "Failed to load messages" });
export const sendChatMessage = (data) => request("/chat/", { method: "POST", body: data, fallback: "Failed to send message" });
export const fetchOwnerInbox = () => request("/chat/inbox");

// AI assistant (SSE stream of agent events)
export function streamAgent(messages, { provider, signal, onEvent }) {
  return streamSSE(`${BASE}/ai/chat`, {
    body: { messages, provider: provider || undefined },
    headers: authHeaders(),
    signal,
    onEvent,
  });
}

// Human-in-the-loop actions drafted by the agent
export const getAction = (id) => request(`/actions/${id}`);
export const confirmAction = (id, data = {}) =>
  request(`/actions/${id}/confirm`, { method: "POST", body: data, fallback: "Could not confirm" });
export const cancelAction = (id) => request(`/actions/${id}/cancel`, { method: "POST", fallback: "Could not cancel" });

// Safety
export const getSafety = (propertyId) => request(`/safety/${propertyId}`, { fallback: "Failed to fetch safety data" });
export const submitSafetyVote = (propertyId, data) =>
  request(`/safety/${propertyId}/vote`, { method: "POST", body: data, fallback: "Vote failed" });

// Forum
export const fetchForumPosts = (params = {}) => request(`/forum/${qs(params)}`, { fallback: "Failed to fetch posts" });
export const createForumPost = (data) => request("/forum/", { method: "POST", body: data, fallback: "Failed" });
export const getForumPost = (postId) => request(`/forum/${postId}`, { fallback: "Post not found" });
export const upvotePost = (postId) => request(`/forum/${postId}/upvote`, { method: "POST", fallback: "Upvote failed" });
export const getComments = (postId) => request(`/forum/${postId}/comments`, { fallback: "Failed to fetch comments" });
export const addComment = (postId, data) =>
  request(`/forum/${postId}/comments`, { method: "POST", body: data, fallback: "Comment failed" });

// Owner tools
export const listingAssistant = (draft) =>
  request("/listing-assistant", { method: "POST", body: draft, fallback: "Assistant unavailable" });
export const fetchMyProperties = () => request("/properties/mine");
export const updateProperty = (id, data) => request(`/properties/${id}`, { method: "PUT", body: data });
export const deleteProperty = (id) => request(`/properties/${id}`, { method: "DELETE" });
export const getVerification = (id) => request(`/properties/${id}/verification`);
export const removeDocument = (id, documentId) => request(`/properties/${id}/documents/${documentId}`, { method: "DELETE" });

export async function downloadPrivateDocument(url, name) {
  const res = await fetch(`${API_ROOT}${url}`, { headers: authHeaders() });
  if (!res.ok) throw new Error("You cannot download this document. Check your login and try again.");
  const blobUrl = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
}

// Admin
export const adminQueue = () => request("/admin/queue");
export const fetchWomenSafety = id => request(`/properties/${id}/women-safety`);
export const submitWomenSafety = (id, data) => request(`/properties/${id}/women-safety`, { method: "POST", body: data });
export const fetchWomenSafetyQueue = (params = {}) => request(`/admin/women-safety${qs(params)}`);
export const decideWomenSafety = (id, data) => request(`/admin/women-safety/${id}`, { method: "POST", body: data });
export const reviewListing = (id, verdict) => request(`/admin/listings/${id}/${verdict}`, { method: "POST" });
export const reviewContent = (kind, id, verdict) => request(`/admin/content/${kind}/${id}/${verdict}`, { method: "POST" });
export const adminDecisions = (limit = 100) => request(`/admin/decisions?limit=${limit}`);
export const adminLLMUsage = () => request("/admin/llm-usage");

// Private reports and admin investigations
export const createCase = data => request("/cases", { method: "POST", body: data });
export const fetchMyCases = (params = {}) => request(`/cases/mine${qs(params)}`);
export const fetchCase = id => request(`/cases/${id}`);
export const sendCaseMessage = (id, body) => request(`/cases/${id}/messages`, { method: "POST", body: { body } });
export const fetchAdminCases = (params = {}) => request(`/admin/cases${qs(params)}`);
export const claimCase = (id, version) => request(`/admin/cases/${id}/claim`, { method: "POST", body: { expected_version: version } });
export const addCaseNote = (id, body, internal) => request(`/admin/cases/${id}/notes`, { method: "POST", body: { body, internal } });
export const decideCase = (id, data) => request(`/admin/cases/${id}`, { method: "PATCH", body: data });

// Scout: background house-hunting agent
export const parseHunt = (brief) => request("/hunts/parse", { method: "POST", body: { brief }, fallback: "Couldn't read that" });
export const createHunt = (data) => request("/hunts", { method: "POST", body: data, fallback: "Couldn't save the hunt" });
export const listHunts = () => request("/hunts");
export const getHunt = (id) => request(`/hunts/${id}`);
export const runHunt = (id) => request(`/hunts/${id}/run`, { method: "POST", fallback: "Scout couldn't run" });
export const updateHunt = (id, data) => request(`/hunts/${id}`, { method: "PATCH", body: data });
export const deleteHunt = (id) => request(`/hunts/${id}`, { method: "DELETE" });
