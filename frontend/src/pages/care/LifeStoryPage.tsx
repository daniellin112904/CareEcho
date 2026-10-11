import { useCallback, useEffect, useState, type FormEvent } from "react";
import { addPassage, deletePassage, listPassages, LIFE_STORY_TOPICS, type Passage } from "../../api";

const EMPTY = { topic: "family" as Passage["topic"], passage: "", people: "", said_by: "", sensitive: false };

export default function LifeStoryPage() {
  const [passages, setPassages] = useState<Passage[] | null>(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState(EMPTY);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [added, setAdded] = useState(false);

  const reload = useCallback(() => {
    listPassages()
      .then((data) => {
        setPassages(data.passages);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(reload, [reload]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    setAdded(false);
    try {
      await addPassage(form);
      setForm(EMPTY);
      setAdded(true);
      reload();
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(passage: Passage) {
    if (!window.confirm("Delete this passage? Vela will stop using it.")) return;
    try {
      await deletePassage(passage.id);
    } catch (err) {
      setError((err as Error).message);
    }
    reload();
  }

  return (
    <>
      <section className="care-section">
        <h1>Life story</h1>
        <p className="care-lede">
          The patient's past: family, home, work, what they love. Vela uses it to talk about the past, never for plans.
          Write one or two sentences, use names rather than "she" or "he", and never include medicine.
        </p>
        <form className="clone-form" onSubmit={submit}>
          <label className="care-field">
            Topic
            <select value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value as Passage["topic"] })}>
              {LIFE_STORY_TOPICS.map((t) => (
                <option key={t} value={t}>
                  {t[0].toUpperCase() + t.slice(1)}
                </option>
              ))}
            </select>
          </label>
          <label className="care-field">
            Passage (at least 10 characters)
            <textarea
              rows={3}
              required
              minLength={10}
              maxLength={400}
              placeholder="Rose grew up in Ponce, Puerto Rico, and moved to New York with Joe in 1968."
              value={form.passage}
              onChange={(e) => setForm({ ...form, passage: e.target.value })}
            />
          </label>
          <label className="care-field">
            People named in it
            <input
              maxLength={200}
              placeholder="Joe, Anna"
              value={form.people}
              onChange={(e) => setForm({ ...form, people: e.target.value })}
            />
          </label>
          <label className="care-field">
            Who it came from (required)
            <input
              required
              maxLength={100}
              placeholder="Anna, daughter"
              value={form.said_by}
              onChange={(e) => setForm({ ...form, said_by: e.target.value })}
            />
          </label>
          <label className="care-check">
            <input
              type="checkbox"
              checked={form.sensitive}
              onChange={(e) => setForm({ ...form, sensitive: e.target.checked })}
            />
            Sensitive: Vela speaks of it gently and never brings it up first
          </label>
          <button className="care-primary" disabled={saving}>
            {saving ? "Saving" : "Add passage"}
          </button>
          {formError && <p className="care-error">{formError}</p>}
          {added && <p className="care-success">Added. Vela can find it in about a minute.</p>}
        </form>
      </section>

      <section className="care-section">
        <h2>Passages</h2>
        {error && <p className="care-error">{error}</p>}
        {passages && passages.length === 0 && <p className="care-notice">No passages yet.</p>}
        {passages && passages.length > 0 && (
          <ul className="message-list">
            {passages.map((p) => (
              <li key={p.id} className="message-row">
                <div className="message-head">
                  <span className="memory-status">{p.topic}</span>
                  {p.sensitive && (
                    <span className="memory-status" data-status="pending">
                      Sensitive
                    </span>
                  )}
                  <span className="message-when">
                    {[p.people, p.said_by && `from ${p.said_by}`].filter(Boolean).join(" · ")}
                  </span>
                  <button className="care-quiet" onClick={() => remove(p)}>
                    Delete
                  </button>
                </div>
                <p className="message-text">{p.passage}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
