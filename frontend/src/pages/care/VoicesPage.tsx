import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  cloneVoice,
  createFamilyMessage,
  deleteFamilyMessage,
  deleteVoice,
  familyMessageAudioUrl,
  listFamilyMessages,
  listVoices,
  type FamilyMessage,
  type Voice,
} from "../../api";
import { toWav, useRecorder } from "./recording";

const MIN_SECONDS = 10;
const MAX_MESSAGE = 500;

export default function VoicesPage() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [messages, setMessages] = useState<FamilyMessage[]>([]);
  const [loadError, setLoadError] = useState("");

  function refresh() {
    Promise.all([listVoices(), listFamilyMessages()])
      .then(([v, m]) => {
        setVoices(v.voices);
        setMessages(m.messages);
        setLoadError("");
      })
      .catch((err: Error) => setLoadError(err.message));
  }

  useEffect(refresh, []);

  async function removeVoice(voice: Voice) {
    if (!confirm(`Delete the voice "${voice.name}" and its messages? This can't be undone.`)) return;
    try {
      await deleteVoice(voice.voice_id);
      refresh();
    } catch (err) {
      setLoadError((err as Error).message);
    }
  }

  async function removeMessage(message: FamilyMessage) {
    if (!confirm(`Delete this message from ${message.from_name}?`)) return;
    try {
      await deleteFamilyMessage(message.id);
      refresh();
    } catch (err) {
      setLoadError((err as Error).message);
    }
  }

  return (
    <>
      <section className="care-section">
        <h1>Family messages</h1>
        <p className="care-lede">
          Write a short message and it's read aloud in a family member's own voice on the patient screen. The
          companion itself always speaks in its own neutral voice, so the patient never hears a cloned voice
          saying words the family didn't write.
        </p>
        {loadError && <p className="care-error">{loadError}</p>}
        {voices.length > 0 ? (
          <MessageForm voices={voices} onCreated={refresh} />
        ) : (
          <p className="care-notice">Add a family voice below to write the first message.</p>
        )}
        {messages.length > 0 && (
          <ul className="message-list">
            {messages.map((message, i) => (
              <li key={message.id} className="message-row">
                <div className="message-head">
                  <span className="message-from">From {message.from_name}</span>
                  {i === 0 && <span className="voice-current">On patient screen</span>}
                  <span className="message-when">{formatWhen(message.created_at)}</span>
                  <button className="care-quiet" onClick={() => removeMessage(message)}>
                    Delete
                  </button>
                </div>
                <p className="message-text">{message.text}</p>
                <audio controls preload="none" src={familyMessageAudioUrl(message.id)} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="care-section">
        <h2>Family voices</h2>
        <p className="care-lede">Voices cloned with the person's consent. They only read the messages above.</p>
        {voices.length > 0 && (
          <ul className="voice-list">
            {voices.map((voice) => (
              <li key={voice.voice_id} className="voice-row">
                <span className="voice-name">{voice.name}</span>
                <button className="care-quiet" onClick={() => removeVoice(voice)} aria-label={`Delete ${voice.name}`}>
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <CloneVoiceForm onCreated={refresh} />
    </>
  );
}

function MessageForm({ voices, onCreated }: { voices: Voice[]; onCreated: () => void }) {
  const [voiceId, setVoiceId] = useState(voices[0].voice_id);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await createFamilyMessage(voiceId, text.trim());
      setText("");
      onCreated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="clone-form message-form" onSubmit={submit}>
      <label className="care-field">
        Voice
        <select value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>
          {voices.map((voice) => (
            <option key={voice.voice_id} value={voice.voice_id}>
              {voice.name}
            </option>
          ))}
        </select>
      </label>
      <label className="care-field">
        Message
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={MAX_MESSAGE}
          rows={3}
          placeholder="Hi Mom, it's Anna. I'll see you at two tomorrow. Love you."
        />
      </label>
      {error && <p className="care-error">{error}</p>}
      <button className="care-primary" disabled={!text.trim() || saving}>
        {saving ? "Creating message" : "Create message"}
      </button>
    </form>
  );
}

function formatWhen(iso: string) {
  return new Date(iso).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });
}

function CloneVoiceForm({ onCreated }: { onCreated: () => void }) {
  const recorder = useRecorder();
  const [name, setName] = useState("");
  const [upload, setUpload] = useState<{ wav: Blob; name: string } | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [consent, setConsent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ text: "", error: false });

  const sample = upload?.wav ?? recorder.audio;
  const previewUrl = useMemo(() => (sample ? URL.createObjectURL(sample) : ""), [sample]);
  useEffect(() => () => URL.revokeObjectURL(previewUrl), [previewUrl]);

  const tooShort = !upload && recorder.audio !== null && recorder.seconds < MIN_SECONDS;
  const ready = name.trim() && sample && !tooShort && consent && !saving;

  function clearUpload() {
    setUpload(null);
    setUploadError("");
  }

  async function pickFile(file: File | undefined) {
    clearUpload();
    recorder.clear();
    if (!file) return;
    try {
      const { wav, seconds } = await toWav(file);
      if (seconds < MIN_SECONDS) {
        setUploadError(`That file is ${Math.round(seconds)} seconds long. Use one that's at least ${MIN_SECONDS} seconds.`);
      } else {
        setUpload({ wav, name: file.name });
      }
    } catch {
      setUploadError("This file can't be read as audio. Try an MP3, WAV, or M4A recording.");
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!sample) return;
    setSaving(true);
    setMessage({ text: "", error: false });
    try {
      const wav = upload?.wav ?? (await toWav(sample)).wav;
      await cloneVoice(name.trim(), wav, "sample.wav");
      setMessage({ text: `${name.trim()} is ready. You can write a message in their voice above.`, error: false });
      setName("");
      clearUpload();
      setConsent(false);
      recorder.clear();
      onCreated();
    } catch (err) {
      setMessage({ text: (err as Error).message, error: true });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="care-section">
      <h2>Add a voice</h2>
      <p className="care-lede">
        Record someone the patient knows reading aloud for at least {MIN_SECONDS} seconds, in a quiet room. You can
        also upload a recording.
      </p>

      <form className="clone-form" onSubmit={submit}>
        <label className="care-field">
          Whose voice is this?
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Anna, daughter" maxLength={60} />
        </label>

        <div className="clone-sample">
          {recorder.recording ? (
            <button type="button" className="record-button" data-recording onClick={recorder.stop}>
              Stop recording
            </button>
          ) : (
            <button
              type="button"
              className="record-button"
              onClick={() => {
                clearUpload();
                recorder.start();
              }}
            >
              {recorder.audio ? "Record again" : "Record"}
            </button>
          )}
          <span className="record-time" data-short={recorder.recording && recorder.seconds < MIN_SECONDS}>
            {formatSeconds(recorder.recording || recorder.audio ? recorder.seconds : 0)}
            {recorder.recording && recorder.seconds < MIN_SECONDS && ` of at least ${formatSeconds(MIN_SECONDS)}`}
          </span>
          <label className="care-quiet upload-label">
            Upload a file
            <input
              type="file"
              accept="audio/*"
              className="visually-hidden"
              onChange={(e) => {
                pickFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </label>
        </div>

        {recorder.error && <p className="care-error">{recorder.error}</p>}
        {uploadError && <p className="care-error">{uploadError}</p>}
        {tooShort && <p className="care-error">That recording is under {MIN_SECONDS} seconds. Record again a little longer.</p>}
        {previewUrl && !recorder.recording && (
          <div className="clone-preview">
            {upload && <span>{upload.name}</span>}
            <audio controls src={previewUrl} />
          </div>
        )}

        <label className="care-check">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          The person in this recording agreed to have their voice cloned for Vela.
        </label>

        {message.text && <p className={message.error ? "care-error" : "care-success"}>{message.text}</p>}

        <button className="care-primary" disabled={!ready}>
          {saving ? "Creating voice" : "Create voice"}
        </button>
      </form>
    </section>
  );
}

function formatSeconds(total: number) {
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
