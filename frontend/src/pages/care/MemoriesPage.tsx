import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  cancelMemory,
  cancelPatientReminder,
  confirmMemory,
  getCurrentMemories,
  getMemoryHistory,
  getPatient,
  listPatientReminders,
  listPendingMemories,
  listSessions,
  rejectMemory,
  sendReminderNow,
  submitTranscript,
  type CaregiverSession,
  type Certainty,
  type ExtractionResult,
  type Memory,
  type PendingMemory,
} from "../../api";
import { timeWords, whenWords } from "../../when";

export default function MemoriesPage() {
  const [memories, setMemories] = useState<Memory[] | null>(null);
  const [pending, setPending] = useState<PendingMemory[] | null>(null);
  const [pendingError, setPendingError] = useState("");
  const [error, setError] = useState("");
  const [sent, setSent] = useState<Record<string, string>>({});
  const [sessions, setSessions] = useState<CaregiverSession[] | null>(null);
  const [asked, setAsked] = useState<Memory[] | null>(null);
  const [askedError, setAskedError] = useState("");
  const [patientName, setPatientName] = useState<string | null>(null);

  // After any action both lists change: a confirmed update replaces the current version
  const reload = useCallback(() => {
    getCurrentMemories()
      .then((data) => setMemories(data.memories))
      .catch((err: Error) => setError(err.message));
    listPendingMemories()
      .then((data) => {
        setPending(data.pending);
        setPendingError("");
      })
      .catch((err: Error) => setPendingError(err.message));
    listSessions()
      .then((data) => setSessions(data.sessions))
      .catch(() => setSessions(null));
    listPatientReminders()
      .then((data) => {
        setAsked(data.reminders);
        setAskedError("");
      })
      .catch((err: Error) => setAskedError(err.message));
    getPatient()
      .then((data) => setPatientName(data.name))
      .catch(() => {});
  }, []);

  useEffect(reload, [reload]);

  async function remindNow(memory: Memory) {
    try {
      const reminder = await sendReminderNow(memory.id);
      setSent((current) => ({ ...current, [memory.id]: reminder.text }));
      setError("");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function cancel(memory: Memory) {
    if (!window.confirm(`Cancel "${memory.summary}"? Vela will stop mentioning it.`)) return;
    try {
      await cancelMemory(memory.id);
      setError("");
    } catch (err) {
      setError((err as Error).message);
    }
    reload();
  }

  return (
    <>
      <section className="care-section">
        <h1>Memories</h1>
        <p className="care-lede">
          What Vela is allowed to tell the patient. It never answers from anything else. Confirmed plans are also
          spoken as reminders 30 and 5 minutes before; "Remind now" sends one straight away.
        </p>
        <TranscriptForm onAdded={reload} />
      </section>

      <section className="care-section">
        <h2>To review</h2>
        <p className="care-lede">Nothing here is said to the patient until you confirm it.</p>
        {pendingError && <p className="care-error">{pendingError}</p>}
        {pending && pending.length === 0 && <p className="care-notice">Nothing is waiting for review.</p>}
        {pending && pending.length > 0 && (
          <ul className="memory-list">
            {pending.map((m) => (
              <ReviewCard key={m.id} memory={m} onDone={reload} />
            ))}
          </ul>
        )}
      </section>

      <section className="care-section">
        <h2>Current</h2>
        {error && <p className="care-error">{error}</p>}
        {memories && memories.length === 0 && <p className="care-notice">No current memories.</p>}
        <ul className="memory-list">
          {memories?.map((m) => (
            <li key={m.id} className="memory-row">
              <span className="memory-summary">{m.summary}</span>
              {m.event_at && <span className="memory-when">{formatWhen(m)}</span>}
              <span className="memory-status" data-status={m.status}>
                {m.status}
              </span>
              {m.status === "confirmed" && m.event_at && (
                <button className="care-secondary" onClick={() => remindNow(m)}>
                  Remind now
                </button>
              )}
              <button className="care-quiet" onClick={() => cancel(m)}>
                Cancel plan
              </button>
              {sent[m.id] && <p className="memory-sent">Sent to the patient screen: "{sent[m.id]}"</p>}
              {m.supersedes_id && <History id={m.id} />}
            </li>
          ))}
        </ul>
      </section>

      <AskedReminders name={patientName} reminders={asked} error={askedError} onDone={reload} />

      {sessions && sessions.length > 0 && <RecentNotes sessions={sessions} />}
    </>
  );
}

function TranscriptForm({ onAdded }: { onAdded: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ExtractionResult | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await submitTranscript(text));
      setText("");
      onAdded();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const count = result?.candidates.length ?? 0;
  return (
    <form className="clone-form" onSubmit={submit}>
      <label className="care-field">
        What a caregiver said
        <textarea
          rows={4}
          maxLength={4000}
          placeholder="Anna will pick her up at two tomorrow for the dentist at three."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      <button className="care-primary" disabled={!text.trim() || busy}>
        {busy ? "Reading it, a few seconds" : "Turn into memories"}
      </button>
      {error && <p className="care-error">{error}</p>}
      {result && (
        <div aria-live="polite">
          <p className={count ? "care-success" : "memory-when"}>
            {count
              ? `${count} ${count === 1 ? "memory" : "memories"} to review below.`
              : "No plans to save were found in that."}
          </p>
          {result.dropped.length > 0 && (
            <ul className="dropped-list">
              {result.dropped.map((d, i) => (
                <li key={i}>
                  Not saved{d.summary ? `: ${d.summary}` : ""}. {d.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </form>
  );
}

function ReviewCard({ memory, onDone }: { memory: PendingMemory; onDone: () => void }) {
  const [certainty, setCertainty] = useState<Certainty>(memory.certainty ?? "definite");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      onDone();
    }
  }

  // Only send a certainty when staff changed what extraction proposed
  const changedCertainty = certainty !== (memory.certainty ?? "definite") ? certainty : undefined;
  const changes = memory.replaces ? diff(memory.replaces, memory) : [];

  return (
    <li className="review-card">
      <div className="alert-head">
        <span className="memory-status" data-status="pending">
          {memory.replaces ? "Change to a plan" : "New"}
        </span>
        {memory.event_at && <span className="memory-when">{formatWhen(memory)}</span>}
      </div>
      <p className="alert-message">{memory.summary}</p>
      {detailWords(memory) && <p className="memory-when">{detailWords(memory)}</p>}

      {memory.replaces && (
        <div className="review-changes">
          <p className="receipt-label">Replaces "{memory.replaces.summary}"</p>
          {changes.length > 0 ? (
            <ul>
              {changes.map(([label, before, after]) => (
                <li key={label}>
                  {label}: <s>{before || "not said"}</s> → <strong>{after || "not said"}</strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="memory-when">Nothing differs from the current version.</p>
          )}
        </div>
      )}

      {memory.source_quote && <blockquote className="receipt-quote">"{memory.source_quote}"</blockquote>}

      {memory.warnings.length > 0 && (
        <ul className="review-warnings">
          {memory.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      {memory.stale ? (
        <p className="care-error">Already changed. Reject this one.</p>
      ) : (
        <fieldset className="review-certainty">
          <legend className="visually-hidden">How certain is it?</legend>
          {(["definite", "tentative"] as const).map((value) => (
            <label key={value} className="care-check">
              <input
                type="radio"
                name={`certainty-${memory.id}`}
                checked={certainty === value}
                onChange={() => setCertainty(value)}
              />
              {value === "definite" ? "Definite" : "Not certain yet"}
            </label>
          ))}
        </fieldset>
      )}

      {error && <p className="care-error">{error}</p>}
      <div className="toast-actions">
        <button
          className="care-primary"
          disabled={busy || memory.stale}
          onClick={() => run(() => confirmMemory(memory.id, changedCertainty))}
        >
          Confirm
        </button>
        <button className="care-secondary" disabled={busy} onClick={() => run(() => rejectMemory(memory.id))}>
          Reject
        </button>
      </div>
    </li>
  );
}

/** Reminders the patient asked Vela for, in her own words. Said once at their time, never as facts. */
function AskedReminders({
  name,
  reminders,
  error,
  onDone,
}: {
  name: string | null;
  reminders: Memory[] | null;
  error: string;
  onDone: () => void;
}) {
  const [cancelError, setCancelError] = useState("");
  const who = name ?? "the patient";

  async function cancel(reminder: Memory) {
    if (!window.confirm(`Cancel the reminder to "${reminder.summary}"? Vela won't say it.`)) return;
    try {
      await cancelPatientReminder(reminder.id);
      setCancelError("");
    } catch (err) {
      setCancelError((err as Error).message);
    }
    onDone();
  }

  return (
    <section className="care-section">
      <h2>{name ? `${name}'s own reminders` : "The patient's own reminders"}</h2>
      <p className="care-lede">
        Reminders {who} asked Vela for. Each is said once, at its time. They aren't plans, so Vela never tells them as
        facts.
      </p>
      {error && <p className="care-error">{error}</p>}
      {cancelError && <p className="care-error">{cancelError}</p>}
      {reminders && reminders.length === 0 && <p className="care-notice">No upcoming reminders.</p>}
      {reminders && reminders.length > 0 && (
        <ul className="memory-list">
          {reminders.map((r) => (
            <li key={r.id} className="review-card">
              <div className="alert-head">
                <span className="memory-status">Set by {who}</span>
                {r.event_at && <span className="memory-when">{formatWhen(r)}</span>}
              </div>
              <p className="alert-message">{r.summary}</p>
              {r.source_quote && <blockquote className="receipt-quote">"{r.source_quote}"</blockquote>}
              <div className="toast-actions">
                <button className="care-quiet" onClick={() => cancel(r)}>
                  Cancel reminder
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function History({ id }: { id: string }) {
  const [versions, setVersions] = useState<Memory[] | null>(null);
  const [error, setError] = useState("");

  function load() {
    if (versions) return;
    getMemoryHistory(id)
      .then((data) => setVersions(data.versions))
      .catch((err: Error) => setError(err.message));
  }

  return (
    <details className="receipt memory-history" onToggle={(e) => e.currentTarget.open && load()}>
      <summary>
        <span className="receipt-label">What changed</span>
      </summary>
      <div className="receipt-body">
        {error && <p className="care-error">{error}</p>}
        {versions?.map((v, i) => (
          <div key={v.id}>
            <p className="memory-when">
              {i === 0 ? "First" : `Change ${i}`} · <span className="memory-status" data-status={v.status}>{v.status}</span>
            </p>
            {i === 0 ? (
              <p className="history-line">
                {v.summary}
                {v.event_at && `, ${formatWhen(v)}`}
                {detailWords(v) && `. ${detailWords(v)}`}
              </p>
            ) : (
              <ul className="history-line">
                {diff(versions[i - 1], v).map(([label, before, after]) => (
                  <li key={label}>
                    {label}: {before || "not said"} → {after || "not said"}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}

function RecentNotes({ sessions }: { sessions: CaregiverSession[] }) {
  return (
    <section className="care-section">
      <h2>Recent notes</h2>
      <p className="care-lede">What caregivers said, and what became of it. Notes are kept even when reading them failed.</p>
      <ul className="message-list">
        {sessions.map((s) => (
          <li key={s.id} className="message-row">
            <div className="message-head">
              <span className="message-when">
                {new Date(s.created_at).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })}
              </span>
              {s.error ? (
                <span className="alert-kind">Couldn't be read</span>
              ) : !s.finished ? (
                <span className="memory-status">Not finished</span>
              ) : (
                <span className="memory-status">
                  {s.memories.length} {s.memories.length === 1 ? "memory" : "memories"}
                </span>
              )}
            </div>
            <blockquote className="receipt-quote">"{s.transcript}"</blockquote>
            {s.error && <p className="care-error">{s.error}</p>}
            {s.memories.length > 0 && (
              <div className="receipts">
                {s.memories.map((m) => (
                  <span key={m.id} className="note-memory">
                    {m.summary}
                    <span className="memory-status" data-status={m.status}>
                      {m.status}
                    </span>
                  </span>
                ))}
              </div>
            )}
            {s.dropped.length > 0 && (
              <ul className="dropped-list">
                {s.dropped.map((d, i) => (
                  <li key={i}>
                    Not saved{d.summary ? `: ${d.summary}` : ""}. {d.reason}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

type Version = Pick<Memory, "summary" | "event_at" | "all_day" | "details">;

function formatWhen(memory: Version) {
  return whenWords(new Date(memory.event_at!), new Date(), memory.all_day);
}

function detail(memory: Version, key: string) {
  const value = memory.details?.[key];
  if (typeof value !== "string") return "";
  return key === "pickup_at" ? timeWords(new Date(value)) : value;
}

function detailWords(memory: Version) {
  const who = detail(memory, "who");
  const pickup = detail(memory, "pickup_at");
  const place = detail(memory, "place");
  return [who && `With ${who}`, pickup && `pickup at ${pickup}`, place && `at ${place}`].filter(Boolean).join(" · ");
}

/** [label, before, after] for each part that differs between two versions of a plan */
function diff(before: Version, after: Version) {
  const parts: [string, (m: Version) => string][] = [
    ["Plan", (m) => m.summary],
    ["When", (m) => (m.event_at ? formatWhen(m) : "")],
    ["Who", (m) => detail(m, "who")],
    ["Pickup", (m) => detail(m, "pickup_at")],
    ["Place", (m) => detail(m, "place")],
  ];
  return parts
    .map(([label, read]) => [label, read(before), read(after)] as const)
    .filter(([, a, b]) => a !== b);
}
