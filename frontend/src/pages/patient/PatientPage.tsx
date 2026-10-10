import { useEffect, useRef, useState } from "react";
import { ConversationProvider, useConversation, useConversationControls, useConversationStatus } from "@elevenlabs/react";
import {
  familyMessageAudioUrl,
  getCurrentMemories,
  getLatestFamilyMessage,
  startVoiceSession,
  type FamilyMessage,
  type Memory,
} from "../../api";
import Orb, { type OrbMode } from "../../voice/Orb";
import "./patient.css";

export default function PatientPage() {
  return (
    <ConversationProvider>
      <main className="patient">
        <Clock />
        <Companion />
        <section className="patient-tray">
          <ComingUp />
          <FamilyMessageCard />
        </section>
      </main>
    </ConversationProvider>
  );
}

function Companion() {
  const [starting, setStarting] = useState(false);
  const [caption, setCaption] = useState("");
  const [error, setError] = useState("");

  const conversation = useConversation({
    onMessage: ({ role, message }) => role === "agent" && setCaption(lastSentences(message)),
    onError: () => setError("I'm having trouble hearing you. Tap the circle to try again."),
  });
  const { status, isSpeaking, getInputVolume, getOutputVolume } = conversation;
  const live = status === "connected";
  const busy = starting || status === "connecting";

  async function toggle() {
    if (live || busy) {
      conversation.endSession();
      return;
    }
    setError("");
    setCaption("");
    setStarting(true);
    try {
      const session = await startVoiceSession();
      conversation.startSession({
        conversationToken: session.token,
        connectionType: "webrtc",
        dynamicVariables: session.dynamic_variables,
      });
    } catch {
      setError("I can't connect right now. Tap the circle to try again.");
    } finally {
      setStarting(false);
    }
  }

  const mode: OrbMode = busy ? "connecting" : live ? (isSpeaking ? "speaking" : "listening") : "idle";
  const label = {
    idle: "Talk to me",
    connecting: "One moment…",
    listening: "I'm listening",
    speaking: "Speaking…",
  }[mode];
  const hint = {
    idle: "Tap the circle and ask me anything",
    connecting: "Getting ready to listen",
    listening: "Tap the circle when you're done",
    speaking: "",
  }[mode];

  return (
    <section className="patient-center">
      <Orb
        mode={mode}
        getLevel={() => (isSpeaking ? getOutputVolume() : getInputVolume())}
        onClick={toggle}
        aria-label={live ? "Stop talking" : "Start talking"}
      />
      <p className="patient-status" aria-live="polite">
        {error || label}
      </p>
      {!error &&
        (live && caption ? (
          <p className="patient-caption" aria-live="polite">
            {caption}
          </p>
        ) : (
          <p className="patient-hint">{hint}</p>
        ))}
    </section>
  );
}

function lastSentences(text: string, count = 2) {
  return text.split(/(?<=[.!?])\s+/).slice(-count).join(" ");
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(id);
  }, []);

  const hour = now.getHours();
  const part = hour < 5 ? "at night" : hour < 12 ? "in the morning" : hour < 17 ? "in the afternoon" : hour < 21 ? "in the evening" : "at night";
  const greeting = hour >= 5 && hour < 12 ? "Good morning" : hour >= 12 && hour < 17 ? "Good afternoon" : "Good evening";
  const clock = `${hour % 12 || 12}:${String(now.getMinutes()).padStart(2, "0")}`;

  return (
    <header className="patient-top">
      <div className="patient-bar">
        <span className="patient-mark">Vela</span>
        <span className="patient-pill">
          {clock} {part}
        </span>
      </div>
      <p className="patient-greeting">{greeting}</p>
      <p className="patient-day">
        {now.toLocaleDateString([], { weekday: "long" })}, {now.toLocaleDateString([], { month: "long", day: "numeric" })}
      </p>
    </header>
  );
}

function ComingUp() {
  const [memories, setMemories] = useState<Memory[] | null>(null);
  useEffect(() => {
    const load = () =>
      getCurrentMemories()
        .then((data) => setMemories(data.memories))
        .catch(() => {});
    load();
    // Picks up a plan the caregiver just confirmed without reloading the kiosk
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, []);

  if (!memories) return null;
  const now = new Date();
  const next = memories
    .filter((m) => (m.status === "confirmed" || m.status === "tentative") && m.event_at && new Date(m.event_at) >= now)
    .sort((a, b) => Date.parse(a.event_at!) - Date.parse(b.event_at!))[0];

  return (
    <div className="patient-card">
      {next ? (
        <>
          <p className="patient-card-label">
            Coming up
            {next.status === "tentative" && <span className="patient-tag">Not certain yet</span>}
          </p>
          <p className="patient-card-title">
            {next.summary}, {whenWords(new Date(next.event_at!), now)}
          </p>
          {pickupLine(next) && <p className="patient-card-detail">{pickupLine(next)}</p>}
        </>
      ) : (
        <>
          <p className="patient-card-label">Today</p>
          <p className="patient-card-title">No plans yet today</p>
        </>
      )}
    </div>
  );
}

function FamilyMessageCard() {
  const [message, setMessage] = useState<Omit<FamilyMessage, "voice_id"> | null>(null);
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const { endSession } = useConversationControls();
  const { status } = useConversationStatus();

  useEffect(() => {
    const load = () =>
      getLatestFamilyMessage()
        .then((data) => setMessage(data.message))
        .catch(() => {});
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, []);

  // Only one voice at a time: starting a conversation stops the message
  useEffect(() => {
    if (status === "connecting" || status === "connected") audioRef.current?.pause();
  }, [status]);

  useEffect(() => () => audioRef.current?.pause(), []);

  if (!message) return null;

  function toggle() {
    if (!message) return;
    if (playing) {
      audioRef.current?.pause();
      return;
    }
    // ...and playing the message ends the conversation
    if (status === "connecting" || status === "connected") endSession();
    const audio = new Audio(familyMessageAudioUrl(message.id));
    audio.onplay = () => setPlaying(true);
    audio.onpause = () => setPlaying(false);
    audio.onerror = () => setPlaying(false);
    audioRef.current = audio;
    audio.play().catch(() => setPlaying(false));
  }

  const from = message.from_name;
  return (
    <div className="patient-card patient-message">
      <Orb palette="warm" mode={playing ? "speaking" : "idle"} onClick={toggle} tabIndex={-1} aria-hidden />
      <div className="patient-message-copy">
        <p className="patient-message-title">Recorded message from {from}</p>
        <p className="patient-card-detail">{playing ? `"${message.text}"` : `In ${from}'s own voice`}</p>
      </div>
      <button className="patient-play" onClick={toggle}>
        {playing ? "Stop" : "Play"}
      </button>
    </div>
  );
}

function timeWords(date: Date) {
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function whenWords(date: Date, now: Date) {
  const days = Math.round((startOfDay(date) - startOfDay(now)) / 86_400_000);
  const day =
    days === 0
      ? "today"
      : days === 1
        ? "tomorrow"
        : days < 7
          ? `on ${date.toLocaleDateString([], { weekday: "long" })}`
          : `on ${date.toLocaleDateString([], { month: "long", day: "numeric" })}`;
  return `${day} at ${timeWords(date)}`;
}

function startOfDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function pickupLine(memory: Memory) {
  const { who, pickup_at } = memory.details ?? {};
  if (typeof who !== "string") return "";
  if (typeof pickup_at === "string") return `${who} picks you up at ${timeWords(new Date(pickup_at))}`;
  return `With ${who}`;
}
