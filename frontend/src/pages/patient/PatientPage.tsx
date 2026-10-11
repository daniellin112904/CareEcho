import { useCallback, useEffect, useRef, useState } from "react";
import { ConversationProvider, useConversation, useConversationControls, useConversationStatus } from "@elevenlabs/react";
import {
  familyMessageAudioUrl,
  getAlertStatus,
  getCurrentMemories,
  getLatestFamilyMessage,
  startVoiceSession,
  type FamilyMessage,
  type Memory,
} from "../../api";
import { createAgentSession } from "../../voice/agentTools";
import { startOfDay, timeWords, whenWords } from "../../when";
import Orb, { type OrbMode } from "../../voice/Orb";
import { useReminders } from "./useReminders";
import "./patient.css";

export default function PatientPage() {
  return (
    <ConversationProvider>
      <PatientScreen />
    </ConversationProvider>
  );
}

function PatientScreen() {
  // The open urgent alert, if any: shown until staff mark it resolved
  const [urgentAlertId, setUrgentAlertId] = useState<string | null>(null);
  const clearUrgent = useCallback(() => setUrgentAlertId(null), []);
  const { status } = useConversationStatus();
  const reminders = useReminders(status === "connecting" || status === "connected");

  return (
    <main className="patient">
      <Clock />
      <Companion
        onUrgentAlert={setUrgentAlertId}
        announcement={reminders.speaking ? (reminders.reminder?.text ?? null) : null}
      />
      <section className="patient-tray">
        {/* One card at a time when something needs attention: an emergency first, then a reminder */}
        {urgentAlertId ? (
          <CareTeamToldCard alertId={urgentAlertId} onResolved={clearUrgent} />
        ) : reminders.reminder ? (
          <ReminderCard
            text={reminders.reminder.text}
            speaking={reminders.speaking}
            needsTap={reminders.needsTap}
            onReplay={reminders.replay}
            onDismiss={reminders.dismiss}
          />
        ) : (
          <>
            <ComingUp />
            <FamilyMessageCard />
          </>
        )}
      </section>
    </main>
  );
}

function Companion({
  onUrgentAlert,
  announcement,
}: {
  onUrgentAlert: (alertId: string) => void;
  /** A reminder being spoken right now: the orb speaks and its words show as the caption */
  announcement: string | null;
}) {
  const [starting, setStarting] = useState(false);
  const [caption, setCaption] = useState("");
  const [error, setError] = useState("");
  const agentSession = useRef<ReturnType<typeof createAgentSession> | null>(null);

  const conversation = useConversation({
    onMessage: ({ role, message }) => {
      agentSession.current?.onMessage(role, message);
      if (role === "agent") setCaption(lastSentences(message));
    },
    onConnect: ({ conversationId }) => agentSession.current?.setConversationId(conversationId),
    onDisconnect: () => agentSession.current?.flush(),
    onError: () => setError("I'm having trouble hearing you. Tap the flame to try again."),
  });
  const { status, isSpeaking, getInputVolume, getOutputVolume, sendContextualUpdate } = conversation;
  const live = status === "connected";
  const busy = starting || status === "connecting";

  // The agent only hears the time once, at the start. Without updates it guesses how
  // much time has passed, so tell it the real time every minute (it doesn't reply to these).
  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => sendContextualUpdate(`The time is now ${clockTime(new Date())}.`), 60_000);
    return () => clearInterval(id);
  }, [live, sendContextualUpdate]);

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
      agentSession.current = createAgentSession(session.dynamic_variables.patient_name ?? "The patient", {
        onUrgentAlert,
        tellAgent: sendContextualUpdate,
      });
      conversation.startSession({
        conversationToken: session.token,
        connectionType: "webrtc",
        dynamicVariables: session.dynamic_variables,
        clientTools: agentSession.current.clientTools,
      });
    } catch {
      setError("I can't connect right now. Tap the flame to try again.");
    } finally {
      setStarting(false);
    }
  }

  const announcing = announcement !== null && !live && !busy;
  const mode: OrbMode =
    busy ? "connecting" : live ? (isSpeaking ? "speaking" : "listening") : announcing ? "speaking" : "idle";
  const label = announcing
    ? "A reminder"
    : {
        idle: "Talk to me",
    connecting: "One moment…",
        listening: "I'm listening",
        speaking: "Speaking…",
      }[mode];
  const hint = {
    idle: "Tap the flame and ask me anything",
    connecting: "Getting ready to listen",
    listening: "Tap the flame when you're done",
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
      <div className="patient-words">
        {!error &&
          (announcing || (live && caption) ? (
            <p className="patient-caption" aria-live="polite">
              {announcing ? announcement : caption}
            </p>
          ) : (
            <p className="patient-hint">{hint}</p>
          ))}
      </div>
    </section>
  );
}

function lastSentences(text: string, count = 2) {
  return text.split(/(?<=[.!?])\s+/).slice(-count).join(" ");
}

function clockTime(date: Date) {
  return date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
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
        <span className="patient-mark">
          <img src="/vela-logo.svg" alt="" />
          Vela
        </span>
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
    .filter((m) => (m.status === "confirmed" || m.status === "tentative") && m.event_at && !hasPassed(m, now))
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
            {next.summary}, {whenWords(new Date(next.event_at!), now, next.all_day)}
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

function ReminderCard({
  text,
  speaking,
  needsTap,
  onReplay,
  onDismiss,
}: {
  text: string;
  speaking: boolean;
  needsTap: boolean;
  onReplay: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="patient-card patient-reminder" role="status">
      <div className="patient-reminder-copy">
        <p className="patient-card-label">Reminder</p>
        <p className="patient-card-title">{text}</p>
      </div>
      <div className="patient-reminder-actions">
        <button className="patient-play" onClick={onReplay}>
          {needsTap ? "Hear it" : speaking ? "Speaking…" : "Hear again"}
        </button>
        <button className="patient-ok" onClick={onDismiss}>
          OK
        </button>
      </div>
    </div>
  );
}

function CareTeamToldCard({ alertId, onResolved }: { alertId: string; onResolved: () => void }) {
  useEffect(() => {
    const check = () =>
      getAlertStatus(alertId)
        .then(({ resolved }) => resolved && onResolved())
        .catch(() => {});
    const id = setInterval(check, 5_000);
    return () => clearInterval(id);
  }, [alertId, onResolved]);

  // Says only what is true: the care team was told. Not that help is on the way.
  return (
    <div className="patient-card patient-care-told" role="status">
      <p className="patient-card-title">Your care team has been told</p>
      <p className="patient-card-detail">Stay where you are if you can. You're not alone.</p>
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
      <Orb mode={playing ? "speaking" : "idle"} onClick={toggle} tabIndex={-1} aria-hidden />
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

// An all-day plan ("Anna might visit Saturday") stays up all that day; a timed one until it starts
function hasPassed(memory: Memory, now: Date) {
  const at = new Date(memory.event_at!);
  return memory.all_day ? startOfDay(at) < startOfDay(now) : at < now;
}

function pickupLine(memory: Memory) {
  const { who, pickup_at } = memory.details ?? {};
  if (typeof who !== "string") return "";
  if (typeof pickup_at === "string") return `${who} picks you up at ${timeWords(new Date(pickup_at))}`;
  return `With ${who}`;
}
