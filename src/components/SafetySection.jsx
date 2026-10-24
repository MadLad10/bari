import { useState, useEffect } from "react";
import { getSafety, submitSafetyVote } from "../api";
import { useAuth } from "../auth/AuthContext";
import "./SafetySection.css";
import PropertyLocation from "./PropertyLocation";

const STARS = [1, 2, 3, 4, 5];

function StarRating({ value, onChange, readonly = false }) {
  const [hover, setHover] = useState(0);
  return (
    <div className="stars">
      {STARS.map((s) => (
        <button
          key={s}
          type="button"
          className={`star${(hover || value) >= s ? " filled" : ""}`}
          onClick={() => !readonly && onChange?.(s)}
          onMouseEnter={() => !readonly && setHover(s)}
          onMouseLeave={() => !readonly && setHover(0)}
          disabled={readonly}
        >★</button>
      ))}
    </div>
  );
}

export default function SafetySection({ property }) {
  const { id, address, latitude, longitude } = property;
  const { user, openAuth } = useAuth();

  const [safety, setSafety] = useState(null);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [voterName, setVoterName] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getSafety(id).then(setSafety).catch(() => {});
  }, [id]);

  async function handleVote(e) {
    e.preventDefault();
    if (!rating) return;
    setSubmitting(true);
    try {
      const result = await submitSafetyVote(id, {
        rating,
        comment: comment || null,
        voter_name: voterName || null,
      });
      setSafety((prev) => ({
        ...prev,
        avg_score: result.avg_score,
        vote_count: (prev?.vote_count || 0) + 1,
        votes: [
          { rating, comment, voter_name: voterName || "Anonymous", created_at: new Date().toISOString() },
          ...(prev?.votes || []),
        ],
      }));
      setSubmitted(true);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="safety-section">
      <PropertyLocation property={property} />

      {/* Safety Score */}
      <div className="detail-section">
        <h2>Area Safety</h2>
        <div className="safety-score-row">
          <div className="safety-score-big">
            <span className="score-num">{safety?.avg_score?.toFixed(1) ?? "—"}</span>
            <span className="score-label">/ 5</span>
          </div>
          <div className="safety-score-meta">
            <StarRating value={Math.round(safety?.avg_score || 0)} readonly />
            <span className="vote-count">{safety?.vote_count ?? 0} community rating{safety?.vote_count !== 1 ? "s" : ""}</span>
          </div>
        </div>

        {/* Recent votes */}
        {safety?.votes?.length > 0 && (
          <div className="safety-votes">
            {safety.votes.slice(0, 3).map((v, i) => (
              <div key={i} className="safety-vote-item">
                <div className="vote-header">
                  <StarRating value={v.rating} readonly />
                  <span className="vote-author">{v.voter_name}</span>
                </div>
                {v.comment && <p className="vote-comment">{v.comment}</p>}
              </div>
            ))}
          </div>
        )}

        {/* Vote form */}
        {!user ? (
          <div className="auth-gate">
            Ratings come from logged-in students only.
            <br />
            <button onClick={() => openAuth({ reason: "Log in to rate this area's safety." })}>Log in to rate</button>
          </div>
        ) : !submitted ? (
          <form className="safety-vote-form" onSubmit={handleVote}>
            <p className="vote-form-label">Rate this area's safety</p>
            <StarRating value={rating} onChange={setRating} />
            <input
              value={voterName}
              onChange={(e) => setVoterName(e.target.value)}
              placeholder="Display name (leave blank to stay anonymous)"
            />
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={2}
              placeholder="Share your experience with this area… (optional)"
            />
            <button type="submit" disabled={!rating || submitting}>
              {submitting ? "Submitting…" : "Submit Rating"}
            </button>
          </form>
        ) : (
          <div className="vote-thanks">Thanks for your rating!</div>
        )}
      </div>
    </div>
  );
}
