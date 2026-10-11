import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { getCurrentMemories, getPatient, listPassages, renamePatient, resetDemo, startNewPatient } from "../../api";

export default function PatientInfoPage() {
  const [name, setName] = useState<string | null>(null);
  const [memories, setMemories] = useState<number | null>(null);
  const [passages, setPassages] = useState<number | string | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(() => {
    getPatient()
      .then((data) => setName(data.name))
      .catch((err: Error) => setError(err.message));
    getCurrentMemories()
      .then((data) => setMemories(data.memories.length))
      .catch(() => setMemories(null));
    listPassages()
      .then((data) => setPassages(data.passages.length))
      .catch((err: Error) => setPassages(err.message));
  }, []);

  useEffect(reload, [reload]);

  return (
    <>
      <section className="care-section">
        <h1>{name ?? "Patient"}</h1>
        <p className="care-lede">Who Vela talks to. Changes apply from the next conversation.</p>
        {error && <p className="care-error">{error}</p>}
        {name !== null && <RenameForm key={name} current={name} onSaved={setName} />}
      </section>

      <section className="care-section">
        <h2>What Vela knows</h2>
        <ul className="memory-list">
          <li className="memory-row">
            <span className="memory-summary">
              {memories ?? "–"} current {memories === 1 ? "memory" : "memories"}: plans, people, and facts
            </span>
            <Link className="care-secondary" to="../memories">
              Memories
            </Link>
          </li>
          <li className="memory-row">
            <span className="memory-summary">
              {typeof passages === "number"
                ? `${passages} life story ${passages === 1 ? "passage" : "passages"}`
                : "Life story"}
            </span>
            {typeof passages === "string" && <span className="care-error">{passages}</span>}
            <Link className="care-secondary" to="../life-story">
              Life story
            </Link>
          </li>
        </ul>
      </section>

      <NewPatient onDone={reload} />
      <DemoReset onDone={reload} />
    </>
  );
}

function RenameForm({ current, onSaved }: { current: string; onSaved: (name: string) => void }) {
  const [value, setValue] = useState(current);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      onSaved((await renamePatient(value)).name);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="clone-form" onSubmit={submit}>
      <label className="care-field">
        Name Vela uses
        <input maxLength={60} value={value} onChange={(e) => setValue(e.target.value)} />
      </label>
      <button className="care-primary" disabled={saving || !value.trim() || value.trim() === current}>
        {saving ? "Saving" : "Save name"}
      </button>
      {error && <p className="care-error">{error}</p>}
    </form>
  );
}

function NewPatient({ onDone }: { onDone: () => void }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const confirmed = window.confirm(
      `Start over with ${value.trim()}? This removes every memory, caregiver note, answer, alert, and the life story. Family messages are kept. The database is shared, so this changes it for everyone.`,
    );
    if (!confirmed) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const result = await startNewPatient(value);
      setMessage(`Vela now talks to ${result.name}. Add what Vela should know on the Memories and Life story tabs.`);
      setError(result.life_story_error ?? "");
      setValue("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      onDone();
    }
  }

  return (
    <section className="care-section">
      <h2>Start a new patient</h2>
      <p className="care-lede">
        Vela looks after one patient at a time. A new patient starts with no memories and no life story.
      </p>
      <form className="clone-form" onSubmit={submit}>
        <label className="care-field">
          New patient's name
          <input maxLength={60} value={value} onChange={(e) => setValue(e.target.value)} />
        </label>
        <button className="care-primary" disabled={busy || !value.trim()}>
          {busy ? "Starting over" : "Start new patient"}
        </button>
        {message && <p className="care-success">{message}</p>}
        {error && <p className="care-error">{error}</p>}
      </form>
    </section>
  );
}

function DemoReset({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function reset() {
    const confirmed = window.confirm(
      "Reset to Rose's demo for everyone? Her name, plans, and life story come back, and answers, alerts, and caregiver notes are removed. Family messages are kept.",
    );
    if (!confirmed) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const result = await resetDemo();
      setMessage(`Reset. Rose and her ${result.memories} demo memories are back.`);
      setError(result.life_story_error ?? "");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      onDone();
    }
  }

  return (
    <section className="care-section">
      <h2>Demo</h2>
      <p className="care-lede">Go back to Rose, the demo patient, with her plans timed from now and her life story.</p>
      <button className="care-secondary" disabled={busy} onClick={reset}>
        {busy ? "Resetting" : "Reset to Rose's demo"}
      </button>
      {message && <p className="care-success">{message}</p>}
      {error && <p className="care-error">{error}</p>}
    </section>
  );
}
