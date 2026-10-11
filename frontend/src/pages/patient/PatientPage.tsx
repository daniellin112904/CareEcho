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
import { atTimeWords, startOfDay, whenWords } from "../../when";
import {
  LANGUAGES,
  STRINGS,
  clockPill,
  dateLine,
  firstMessage,
  greeting,
  loadLanguage,
  saveLanguage,
  type Lang,
} from "../../i18n";
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
  const [lang, setLang] = useState<Lang>(loadLanguage);
  // Set while the voice session is being fetched, before the SDK reports "connecting"
  const [starting, setStarting] = useState(false);
  // The open urgent alert, if any: shown until staff mark it resolved
  const [urgentAlertId, setUrgentAlertId] = useState<string | null>(null);
  const clearUrgent = useCallback(() => setUrgentAlertId(null), []);
  const { status } = useConversationStatus();
  const talking = status === "connecting" || status === "connected";
  const reminders = useReminders(talking);

  // Screen readers and fonts follow the chosen language while this screen is open
  useEffect(() => {
    const root = document.documentElement;
    const previous = root.lang;
    root.lang = lang;
    return () => {
      root.lang = previous;
    };
  }, [lang]);

  function chooseLanguage(next: Lang) {
    setLang(next);
    saveLanguage(next);
  }

  return (
    <main className="patient">
      {/* The language is picked before a conversation, never during one */}
      <Clock lang={lang} onLanguage={chooseLanguage} locked={starting || talking} />
      <Companion
        lang={lang}
        starting={starting}
        onStarting={setStarting}
        onUrgentAlert={setUrgentAlertId}
        announcement={reminders.speaking ? (reminders.reminder?.text ?? null) : null}
      />
      <section className="patient-tray">
        {/* One card at a time when something needs attention: an emergency first, then a reminder */}
        {urgentAlertId ? (
          <CareTeamToldCard lang={lang} alertId={urgentAlertId} onResolved={clearUrgent} />
        ) : reminders.reminder ? (
          <ReminderCard
            lang={lang}
            text={reminders.reminder.text}
            speaking={reminders.speaking}
            needsTap={reminders.needsTap}
            onReplay={reminders.replay}
            onDismiss={reminders.dismiss}
          />
        ) : (
          <>
            <ComingUp lang={lang} />
            <FamilyMessageCard lang={lang} />
          </>
        )}
      </section>
    </main>
  );
}

function Companion({
  lang,
  starting,
  onStarting,
  onUrgentAlert,
  announcement,
}: {
  lang: Lang;
  starting: boolean;
  onStarting: (starting: boolean) => void;
  onUrgentAlert: (alertId: string) => void;
  /** A reminder being spoken right now: the orb speaks and its words show as the caption */
  announcement: string | null;
}) {
  const [caption, setCaption] = useState("");
  // A key, not the words, so it shows in whichever language is picked
  const [error, setError] = useState<"" | "errorConnect" | "errorHearing">("");
  const agentSession = useRef<ReturnType<typeof createAgentSession> | null>(null);
  const t = STRINGS[lang];

  const conversation = useConversation({
    onMessage: ({ role, message }) => {
      agentSession.current?.onMessage(role, message);
      if (role === "agent") setCaption(lastSentences(message));
    },
    onConnect: ({ conversationId }) => agentSession.current?.setConversationId(conversationId),
    onDisconnect: () => agentSession.current?.flush(),
    onError: () => setError("errorHearing"),
  });
  const { status, isSpeaking, getInputVolume, getOutputVolume, sendContextualUpdate } = conversation;
  const live = status === "connected";
  const busy = starting || status === "connecting";

  // The agent only hears the time once, at the start. Without updates it guesses how
  // much time has passed, so tell it the real time every minute (it doesn't reply to these).
  // Always in English: the agent reads it, not the patient.
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
    onStarting(true);
    try {
      const session = await startVoiceSession();
      const name = session.dynamic_variables.patient_name;
      agentSession.current = createAgentSession(name ?? "The patient", {
        onUrgentAlert,
        tellAgent: sendContextualUpdate,
      });
      conversation.startSession({
        conversationToken: session.token,
        connectionType: "webrtc",
        dynamicVariables: session.dynamic_variables,
        clientTools: agentSession.current.clientTools,
        // The language picks the agent's language preset (greeting and voice model). The greeting
        // is also sent directly, in case the preset doesn't apply. language_detection still lets
        // the patient switch language mid conversation.
        overrides: { agent: { language: lang, ...(name && { firstMessage: firstMessage(lang, name) }) } },
      });
    } catch {
      setError("errorConnect");
    } finally {
      onStarting(false);
    }
  }

  const announcing = announcement !== null && !live && !busy;
  const mode: OrbMode =
    busy ? "connecting" : live ? (isSpeaking ? "speaking" : "listening") : announcing ? "speaking" : "idle";
  const label = announcing ? t.orb.reminder : t.orb[mode];
  const hint = mode === "speaking" ? "" : t.hint[mode];

  return (
    <section className="patient-center">
      <Orb
        mode={mode}
        getLevel={() => (isSpeaking ? getOutputVolume() : getInputVolume())}
        onClick={toggle}
        aria-label={live ? t.stopTalking : t.startTalking}
      />
      <p className="patient-status" aria-live="polite">
        {/* A bigger target for the same action; keyboard users already have the orb */}
        <button type="button" className="patient-status-button" onClick={toggle} tabIndex={-1}>
          {error ? t[error] : label}
        </button>
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

function Clock({ lang, onLanguage, locked }: { lang: Lang; onLanguage: (lang: Lang) => void; locked: boolean }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="patient-top">
      <div className="patient-bar">
        <span className="patient-mark">
          <img src="/vela-logo.svg" alt="" />
          Vela
        </span>
        <div className="patient-bar-end">
          <label className="patient-pill patient-language">
            <span className="patient-language-label">{STRINGS[lang].language}</span>
            <select value={lang} onChange={(event) => onLanguage(event.target.value as Lang)} disabled={locked}>
              {LANGUAGES.map(({ code, name }) => (
                <option key={code} value={code} lang={code}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <span className="patient-pill">{clockPill(lang, now)}</span>
        </div>
      </div>
      <p className="patient-greeting">{greeting(lang, now)}</p>
      <p className="patient-day">{dateLine(lang, now)}</p>
    </header>
  );
}

function ComingUp({ lang }: { lang: Lang }) {
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
  const t = STRINGS[lang];
  const now = new Date();
  const next = memories
    .filter((m) => (m.status === "confirmed" || m.status === "tentative") && m.event_at && !hasPassed(m, now))
    .sort((a, b) => Date.parse(a.event_at!) - Date.parse(b.event_at!))[0];

  return (
    <div className="patient-card">
      {next ? (
        <>
          <p className="patient-card-label">
            {t.comingUp}
            {next.status === "tentative" && <span className="patient-tag">{t.notCertain}</span>}
          </p>
          <p className="patient-card-title">
            {next.summary}, {whenWords(new Date(next.event_at!), now, next.all_day, lang)}
          </p>
          {pickupLine(next, lang) && <p className="patient-card-detail">{pickupLine(next, lang)}</p>}
        </>
      ) : (
        <>
          <p className="patient-card-label">{t.today}</p>
          <p className="patient-card-title">{t.noPlans}</p>
        </>
      )}
    </div>
  );
}

function ReminderCard({
  lang,
  text,
  speaking,
  needsTap,
  onReplay,
  onDismiss,
}: {
  lang: Lang;
  text: string;
  speaking: boolean;
  needsTap: boolean;
  onReplay: () => void;
  onDismiss: () => void;
}) {
  const t = STRINGS[lang];
  return (
    <div className="patient-card patient-reminder" role="status">
      <div className="patient-reminder-copy">
        <p className="patient-card-label">{t.reminder}</p>
        <p className="patient-card-title">{text}</p>
      </div>
      <div className="patient-reminder-actions">
        <button className="patient-play" onClick={onReplay}>
          {needsTap ? t.hearIt : speaking ? t.orb.speaking : t.hearAgain}
        </button>
        <button className="patient-ok" onClick={onDismiss}>
          {t.ok}
        </button>
      </div>
    </div>
  );
}

function CareTeamToldCard({ lang, alertId, onResolved }: { lang: Lang; alertId: string; onResolved: () => void }) {
  useEffect(() => {
    const check = () =>
      getAlertStatus(alertId)
        .then(({ resolved }) => resolved && onResolved())
        .catch(() => {});
    const id = setInterval(check, 5_000);
    return () => clearInterval(id);
  }, [alertId, onResolved]);

  // Says only what is true: the care team was told. Not that help is on the way.
  const t = STRINGS[lang];
  return (
    <div className="patient-card patient-care-told" role="status">
      <p className="patient-card-title">{t.careToldTitle}</p>
      <p className="patient-card-detail">{t.careToldDetail}</p>
    </div>
  );
}

function FamilyMessageCard({ lang }: { lang: Lang }) {
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

  const t = STRINGS[lang];
  const from = message.from_name;
  return (
    <div className="patient-card patient-message">
      <Orb mode={playing ? "speaking" : "idle"} onClick={toggle} tabIndex={-1} aria-hidden />
      <div className="patient-message-copy">
        <p className="patient-message-title">{t.messageTitle(from)}</p>
        <p className="patient-card-detail">{playing ? `"${message.text}"` : t.messageVoice(from)}</p>
      </div>
      <button className="patient-play" onClick={toggle}>
        {playing ? t.stop : t.play}
      </button>
    </div>
  );
}

// An all-day plan ("Anna might visit Saturday") stays up all that day; a timed one until it starts
function hasPassed(memory: Memory, now: Date) {
  const at = new Date(memory.event_at!);
  return memory.all_day ? startOfDay(at) < startOfDay(now) : at < now;
}

function pickupLine(memory: Memory, lang: Lang) {
  const { who, pickup_at } = memory.details ?? {};
  if (typeof who !== "string") return "";
  if (typeof pickup_at === "string") return STRINGS[lang].pickup(who, atTimeWords(new Date(pickup_at), lang));
  return STRINGS[lang].withWho(who);
}
