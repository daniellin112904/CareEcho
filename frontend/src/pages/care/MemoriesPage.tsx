import { useEffect, useState } from "react";
import { getCurrentMemories, type Memory } from "../../api";

export default function MemoriesPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    getCurrentMemories()
      .then((data) => setMemories(data.memories))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <section className="care-section">
      <h1>Memories</h1>
      <p className="care-lede">What Vela is allowed to tell the patient. It never answers from anything else.</p>
      <p className="care-notice">
        Showing sample data. Reviewing, confirming, and adding memories arrives with the memory system.
      </p>
      {error && <p className="care-error">{error}</p>}
      <ul className="memory-list">
        {memories.map((m) => (
          <li key={m.id} className="memory-row">
            <span className="memory-summary">{m.summary}</span>
            {m.event_at && (
              <span className="memory-when">
                {new Date(m.event_at).toLocaleString([], {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </span>
            )}
            <span className="memory-status" data-status={m.status}>
              {m.status}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
