import { caseTime } from "../lib/cases";

export default function CaseTimeline({ updates }) {
  return <ol className="case-timeline" aria-label="Case updates">{updates.map(update => <li key={update.id} className={update.internal ? "internal" : ""}>
    <div><strong>{update.actor_name}</strong><span>{update.internal ? "Admin-only note" : update.kind.replaceAll("_", " ")}</span><time dateTime={update.created_at}>{caseTime(update.created_at)}</time></div>
    <p>{update.body}</p>
  </li>)}</ol>;
}
