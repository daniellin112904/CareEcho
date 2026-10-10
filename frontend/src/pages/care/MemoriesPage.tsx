import { useEffect, useState } from "react";
import { getCurrentMemories, sendReminderNow, type Memory } from "../../api";

export default function MemoriesPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [error, setError] = useState("");
  const [sent, setSent] = useState<Record<string, string>>({});

  async function remindNow(memory: Memory) {
    try {
      const reminder = await sendReminderNow(memory.id);
      setSent((current) => ({ ...current, [memory.id]: reminder.text }));
      setError("");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    getCurrentMemories()
      .then((data) => setMemories(data.memories))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <section className="care-section">
      <h1>Memories</h1>
      <p className="care-lede">
        What Vela is allowed to tell the patient. It never answers from anything else. Confirmed plans are also
        spoken as reminders 30 and 5 minutes before; "Remind now" sends one straight away.
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
                  // An all-day plan has a day but no time
                  ...(m.all_day ? {} : { hour: "numeric", minute: "2-digit" }),
                })}
              </span>
            )}
            <span className="memory-status" data-status={m.status}>
              {m.status}
            </span>
            {m.status === "confirmed" && m.event_at && (
              <button className="care-secondary" onClick={() => remindNow(m)}>
                Remind now
              </button>
            )}
            {sent[m.id] && <p className="memory-sent">Sent to the patient screen: "{sent[m.id]}"</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}
