import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchForumPosts, createForumPost, getComments, addComment, upvotePost } from "../api";
import AIAssistant from "../components/AIAssistant";
import NavAuth from "../auth/NavAuth";
import { useAuth } from "../auth/AuthContext";
import "./Forum.css";

const TYPE_LABELS = {
  neighborhood: { label: "Neighborhood", icon: "🏘️", color: "#dbeafe", text: "#1d4ed8" },
  experience:   { label: "Experience",   icon: "💬", color: "#fef9c3", text: "#92400e" },
  roommate:     { label: "Roommate",     icon: "🤝", color: "#dcfce7", text: "#15803d" },
  report:       { label: "Report",       icon: "⚑",  color: "#fee2e2", text: "#991b1b" },
};

const UNIVERSITIES = [
  "BRAC University", "North South University", "BUET",
  "Dhaka University", "Jahangirnagar University", "IUT", "AIUB", "AUST",
];

function TypeBadge({ type }) {
  const t = TYPE_LABELS[type] || TYPE_LABELS.neighborhood;
  return (
    <span className="type-badge" style={{ background: t.color, color: t.text }}>
      {t.icon} {t.label}
    </span>
  );
}

function PostCard({ post, onUpvote }) {
  return (
    <div className="post-card">
      <div className="post-card-top">
        <TypeBadge type={post.post_type} />
        {post.area && <span className="post-area">{post.area}</span>}
        {post.nearby_university && <span className="post-uni">🎓 {post.nearby_university}</span>}
      </div>
      <h3 className="post-title">
        <button className="post-title-btn" onClick={() => onUpvote(post.id, "open")}>
          {post.title}
        </button>
      </h3>
      <p className="post-body-preview">{post.body.slice(0, 160)}{post.body.length > 160 ? "…" : ""}</p>
      <div className="post-card-footer">
        <span className="post-author">by {post.author_name}</span>
        <span className="post-time">{new Date(post.created_at).toLocaleDateString("en-BD", { dateStyle: "medium" })}</span>
        <span className="post-comments">💬 {post.comment_count}</span>
        <button className="post-upvote" onClick={() => onUpvote(post.id, "upvote")}>
          ▲ {post.upvotes}
        </button>
      </div>
    </div>
  );
}

function PostModal({ postId, onClose }) {
  const [post, setPost] = useState(null);
  const [comments, setComments] = useState([]);
  const { user, openAuth } = useAuth();
  const [content, setContent] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    import("../api").then(({ getForumPost, getComments }) => {
      getForumPost(postId).then(setPost);
      getComments(postId).then(setComments);
    });
  }, [postId]);

  async function handleComment(e) {
    e.preventDefault();
    if (!content.trim()) return;
    setSending(true);
    try {
      const c = await addComment(postId, { content });
      setComments((prev) => [...prev, c]);
      setContent("");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕</button>
        {!post ? (
          <div className="modal-loading">Loading…</div>
        ) : (
          <>
            <div className="modal-header">
              <TypeBadge type={post.post_type} />
              {post.area && <span className="post-area">{post.area}</span>}
            </div>
            <h2 className="modal-title">{post.title}</h2>
            <p className="modal-meta">by {post.author_name} · {new Date(post.created_at).toLocaleDateString("en-BD")}</p>
            <p className="modal-body">{post.body}</p>

            <div className="modal-comments">
              <h4>{comments.length} Comment{comments.length !== 1 ? "s" : ""}</h4>
              {comments.map((c) => (
                <div key={c.id} className="comment-item">
                  <span className="comment-author">{c.author_name}</span>
                  <p className="comment-content">{c.content}</p>
                  <span className="comment-time">{new Date(c.created_at).toLocaleDateString("en-BD")}</span>
                </div>
              ))}

              {!user ? (
                <div className="auth-gate">
                  <button onClick={() => openAuth({ reason: "Log in to join the conversation." })}>Log in to comment</button>
                </div>
              ) : (
              <form className="comment-form" onSubmit={handleComment}>
                <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder="Add a comment…" rows={3} required />
                <button type="submit" disabled={sending}>{sending ? "Posting…" : "Post Comment"}</button>
              </form>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function NewPostForm({ initial, onCreated, onCancel }) {
  const [form, setForm] = useState({
    title: initial.title || "",
    body: "",
    post_type: initial.type || "neighborhood",
    area: "",
    nearby_university: "",
    property_id: initial.property_id ? parseInt(initial.property_id) : null,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  function handleChange(e) {
    setForm((p) => ({ ...p, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const payload = { ...form, property_id: form.property_id || null, nearby_university: form.nearby_university || null, area: form.area || null };
      const post = await createForumPost(payload);
      onCreated(post);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="new-post-form">
      <div className="new-post-header">
        <h2>New Post</h2>
        <button className="modal-close" onClick={onCancel}>✕</button>
      </div>
      <form onSubmit={handleSubmit}>
        <div className="npf-field">
          <label>Type</label>
          <div className="type-tabs">
            {Object.entries(TYPE_LABELS).map(([k, v]) => (
              <button key={k} type="button"
                className={`type-tab${form.post_type === k ? " active" : ""}`}
                style={form.post_type === k ? { background: v.color, color: v.text, borderColor: v.text } : {}}
                onClick={() => setForm((p) => ({ ...p, post_type: k }))}>
                {v.icon} {v.label}
              </button>
            ))}
          </div>
        </div>
        <div className="npf-field">
          <label>Title *</label>
          <input name="title" value={form.title} onChange={handleChange} required placeholder="What's your post about?" />
        </div>
        <div className="npf-field">
          <label>Details *</label>
          <textarea name="body" value={form.body} onChange={handleChange} required rows={4} placeholder="Share the full story…" />
        </div>
        <div className="npf-row">
          <div className="npf-field">
            <label>Neighborhood</label>
            <input name="area" value={form.area} onChange={handleChange} placeholder="e.g. Dhanmondi" />
          </div>
          <div className="npf-field">
            <label>University</label>
            <select name="nearby_university" value={form.nearby_university} onChange={handleChange}>
              <option value="">Any / not applicable</option>
              {UNIVERSITIES.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>
        </div>
        {error && <div className="npf-error">{error}</div>}
        <div className="npf-actions">
          <button type="button" className="npf-cancel" onClick={onCancel}>Cancel</button>
          <button type="submit" className="npf-submit" disabled={submitting}>{submitting ? "Posting…" : "Publish Post"}</button>
        </div>
      </form>
    </div>
  );
}

export default function Forum() {
  const [searchParams] = useSearchParams();
  const { user, openAuth } = useAuth();
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ post_type: "", area: "", nearby_university: "", q: "" });
  const [activePost, setActivePost] = useState(null);
  const [showNewForm, setShowNewForm] = useState(
    searchParams.get("type") === "report" || searchParams.get("new") === "1"
  );
  const initialForm = {
    type: searchParams.get("type") || "",
    title: searchParams.get("title") ? decodeURIComponent(searchParams.get("title")) : "",
    property_id: searchParams.get("property_id") || null,
  };

  useEffect(() => { load(); }, [filters]);

  async function load() {
    setLoading(true);
    try { setPosts(await fetchForumPosts(filters)); }
    finally { setLoading(false); }
  }

  async function handleUpvote(postId, action) {
    if (action === "open") { setActivePost(postId); return; }
    if (!user) { openAuth({ reason: "Log in to upvote posts." }); return; }
    const result = await upvotePost(postId);
    setPosts((prev) => prev.map((p) => p.id === postId ? { ...p, upvotes: result.upvotes } : p));
  }

  function handleCreated(post) {
    setPosts((prev) => [post, ...prev]);
    setShowNewForm(false);
  }

  return (
    <div className="forum-layout">
      <nav className="browse-nav">
        <Link to="/" className="nav-logo">bari<span>.com</span></Link>
        <div className="browse-nav-right">
          <NavAuth />
          <Link to="/browse" className="back-link">Browse listings</Link>
          <button className="nav-cta" onClick={() => setShowNewForm(true)}>+ New Post</button>
        </div>
      </nav>

      <div className="forum-container">
        <div className="forum-header">
          <div>
            <h1>Community Forum</h1>
            <p>Ask about neighborhoods, share experiences, find roommates, or report unsafe listings.</p>
          </div>
          <button className="forum-new-btn" onClick={() => setShowNewForm(true)}>+ New Post</button>
        </div>

        {/* Filters */}
        <div className="forum-filters">
          <input value={filters.q} onChange={(e) => setFilters((p) => ({ ...p, q: e.target.value }))} placeholder="Search posts…" className="forum-search" />
          <div className="type-filter-tabs">
            {[["", "All"], ...Object.entries(TYPE_LABELS).map(([k, v]) => [k, `${v.icon} ${v.label}`])].map(([k, label]) => (
              <button key={k} className={`tab-btn${filters.post_type === k ? " active" : ""}`}
                onClick={() => setFilters((p) => ({ ...p, post_type: k }))}>
                {label}
              </button>
            ))}
          </div>
          <div className="forum-filter-row">
            <input value={filters.area} onChange={(e) => setFilters((p) => ({ ...p, area: e.target.value }))} placeholder="Filter by area…" />
            <select value={filters.nearby_university} onChange={(e) => setFilters((p) => ({ ...p, nearby_university: e.target.value }))}>
              <option value="">Any university</option>
              {UNIVERSITIES.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>
        </div>

        {/* Posts */}
        {loading ? (
          <div className="forum-loading">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="post-skeleton" />)}</div>
        ) : posts.length === 0 ? (
          <div className="forum-empty">
            <p>No posts yet. Be the first to start a conversation!</p>
            <button className="nav-cta" onClick={() => setShowNewForm(true)}>+ New Post</button>
          </div>
        ) : (
          <div className="posts-list">
            {posts.map((p) => <PostCard key={p.id} post={p} onUpvote={handleUpvote} />)}
          </div>
        )}
      </div>

      {showNewForm && !user && (
        <div className="modal-overlay" onClick={() => setShowNewForm(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="auth-gate">
              Posting needs an account so the community knows who's talking.
              <br />
              <button onClick={() => { setShowNewForm(false); openAuth({ reason: "Log in to post in the forum." }); }}>Log in</button>
            </div>
          </div>
        </div>
      )}

      {showNewForm && user && (
        <div className="modal-overlay" onClick={() => setShowNewForm(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <NewPostForm initial={initialForm} onCreated={handleCreated} onCancel={() => setShowNewForm(false)} />
          </div>
        </div>
      )}

      {activePost && <PostModal postId={activePost} onClose={() => setActivePost(null)} />}
      <AIAssistant />
    </div>
  );
}
