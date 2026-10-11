import { useCallback, useEffect, useRef, useState, type CSSProperties, type HTMLAttributes, type ReactNode } from "react";
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
        announcementProgress={reminders.progress}
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
  announcementProgress,
}: {
  lang: Lang;
  starting: boolean;
  onStarting: (starting: boolean) => void;
  onUrgentAlert: (alertId: string) => void;
  /** A reminder being spoken right now: the orb speaks and its words show as the caption */
  announcement: string | null;
  announcementProgress: () => number;
}) {
  const [caption, setCaption] = useState("");
  const captionAt = useRef(0);
  // A key, not the words, so it shows in whichever language is picked
  const [error, setError] = useState<"" | "errorConnect" | "errorHearing">("");
  const agentSession = useRef<ReturnType<typeof createAgentSession> | null>(null);
  const t = STRINGS[lang];

  const conversation = useConversation({
    onMessage: ({ role, message }) => {
      agentSession.current?.onMessage(role, message);
      if (role === "agent") {
        setCaption(message);
        captionAt.current = performance.now();
      }
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
          <SameSize lang={lang}>{(l) => (error ? STRINGS[l][error] : announcing ? STRINGS[l].orb.reminder : STRINGS[l].orb[mode])}</SameSize>
        </button>
      </p>
      <div className="patient-words">
        {!error &&
          (announcing || (live && caption) ? (
            <Pages
              key={announcing ? announcement : caption}
              className="patient-caption"
              aria-live="polite"
              text={announcing ? announcement : caption}
              progress={
                announcing
                  ? announcementProgress
                  : // No word timings for Vela's replies, so estimate from how long it has been talking
                    () => (performance.now() - captionAt.current) / 1000 / (caption.length / CHARS_PER_SECOND)
              }
            />
          ) : (
            <p className="patient-hint">
              {mode !== "speaking" && <SameSize lang={lang}>{(l) => STRINGS[l].hint[mode]}</SameSize>}
            </p>
          ))}
      </div>
    </section>
  );
}

/**
 * Every language's version of some text, stacked in the same spot with only the chosen one
 * visible. The box is always sized for the longest, so switching language never moves the layout.
 */
function SameSize({ lang, children }: { lang: Lang; children: (lang: Lang) => ReactNode }) {
  return (
    <span className="patient-same">
      {LANGUAGES.map(({ code }) => (
        <span key={code} lang={code} className={code === lang ? undefined : "patient-same-hidden"}>
          {children(code)}
        </span>
      ))}
    </span>
  );
}

// Drawn rather than emoji: Windows shows flag emoji as two letters. Spanish uses Spain's flag.
function Flag({ lang }: { lang: Lang }) {
  return (
    <svg className="patient-flag" viewBox="0 0 30 20" aria-hidden="true">
      {lang === "en" && (
        <>
          <rect width="30" height="20" fill="#fff" />
          {[0, 2, 4, 6, 8, 10, 12].map((i) => (
            <rect key={i} y={(i * 20) / 13} width="30" height={20 / 13} fill="#b22234" />
          ))}
          <rect width="13" height={(7 * 20) / 13} fill="#3c3b6e" />
        </>
      )}
      {lang === "es" && (
        <>
          <rect width="30" height="20" fill="#aa151b" />
          <rect y="5" width="30" height="10" fill="#f1bf00" />
        </>
      )}
      {lang === "zh" && (
        <>
          <rect width="30" height="20" fill="#de2910" />
          {[
            [5, 5, 3],
            [10, 2, 1],
            [12, 4, 1],
            [12, 7, 1],
            [10, 9, 1],
          ].map(([x, y, r]) => (
            <polygon key={`${x},${y}`} points={star(x, y, r)} fill="#ffde00" />
          ))}
        </>
      )}
    </svg>
  );
}

/** Points of a five-pointed star centered on (x, y) with outer radius r */
function star(x: number, y: number, r: number) {
  return Array.from({ length: 10 }, (_, i) => {
    const radius = i % 2 ? r * 0.382 : r;
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    return `${(x + radius * Math.cos(angle)).toFixed(2)},${(y + radius * Math.sin(angle)).toFixed(2)}`;
  }).join(" ");
}

// Roughly how fast Vela speaks, to page through its replies without word timings
const CHARS_PER_SECOND = 14;

/**
 * Text longer than its box, shown a page at a time like subtitles instead of being cut off. The box
 * is a whole number of lines (--lines in CSS), so a page never shows half a line. `progress` is how
 * far the voice has got, from 0 to 1, and picks the page. Key it by the text so new text starts on
 * page one.
 */
function Pages({
  text,
  progress,
  className,
  ...rest
}: { text: string; progress: () => number; className: string } & HTMLAttributes<HTMLDivElement>) {
  const boxRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLParagraphElement>(null);
  const latest = useRef(progress);
  const [page, setPage] = useState(0);

  useEffect(() => {
    latest.current = progress;
  });

  useEffect(() => {
    const id = setInterval(() => {
      if (!boxRef.current || !textRef.current) return;
      // offsetHeight ignores the transform that turns the page, so this is the whole text
      const pages = Math.max(1, Math.ceil(textRef.current.offsetHeight / boxRef.current.clientHeight - 0.01));
      const done = latest.current();
      setPage(Math.min(pages - 1, Math.floor((Number.isFinite(done) ? done : 0) * pages)));
    }, 200);
    return () => clearInterval(id);
  }, []);

  return (
    <div ref={boxRef} className={`patient-pages ${className}`} style={{ "--page": page } as CSSProperties} {...rest}>
      <p ref={textRef}>{text}</p>
    </div>
  );
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
          {/* All three languages in view, one tap each, rather than a dropdown to open first */}
          <div className="patient-languages" role="radiogroup" aria-label={STRINGS[lang].language}>
            {LANGUAGES.map(({ code, name }) => (
              <label key={code} className="patient-language" lang={code}>
                <input
                  type="radio"
                  name="patient-language"
                  value={code}
                  checked={code === lang}
                  onChange={() => onLanguage(code)}
                  disabled={locked}
                />
                <Flag lang={code} />
                {name}
              </label>
            ))}
          </div>
          <span className="patient-pill">
            <SameSize lang={lang}>{(l) => clockPill(l, now)}</SameSize>
          </span>
        </div>
      </div>
      <p className="patient-greeting">
        <SameSize lang={lang}>{(l) => greeting(l, now)}</SameSize>
      </p>
      <p className="patient-day">
        <SameSize lang={lang}>{(l) => dateLine(l, now)}</SameSize>
      </p>
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
  const now = new Date();
  const next = memories
    .filter((m) => (m.status === "confirmed" || m.status === "tentative") && m.event_at && !hasPassed(m, now))
    .sort((a, b) => Date.parse(a.event_at!) - Date.parse(b.event_at!))[0];

  return (
    <div className="patient-card">
      {next ? (
        <>
          <p className="patient-card-label">
            <SameSize lang={lang}>{(l) => STRINGS[l].comingUp}</SameSize>
            {next.status === "tentative" && (
              <span className="patient-tag">
                <SameSize lang={lang}>{(l) => STRINGS[l].notCertain}</SameSize>
              </span>
            )}
          </p>
          <p className="patient-card-title">
            <SameSize lang={lang}>{(l) => `${next.summary}, ${whenWords(new Date(next.event_at!), now, next.all_day, l)}`}</SameSize>
          </p>
          {pickupLine(next, lang) && (
            <p className="patient-card-detail">
              <SameSize lang={lang}>{(l) => pickupLine(next, l)}</SameSize>
            </p>
          )}
        </>
      ) : (
        <>
          <p className="patient-card-label">
            <SameSize lang={lang}>{(l) => STRINGS[l].today}</SameSize>
          </p>
          <p className="patient-card-title">
            <SameSize lang={lang}>{(l) => STRINGS[l].noPlans}</SameSize>
          </p>
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
  return (
    <div className="patient-card patient-reminder" role="status">
      <div className="patient-reminder-copy">
        <p className="patient-card-label">
          <SameSize lang={lang}>{(l) => STRINGS[l].reminder}</SameSize>
        </p>
        <p className="patient-card-title">{text}</p>
      </div>
      <div className="patient-reminder-actions">
        <button className="patient-play" onClick={onReplay}>
          <SameSize lang={lang}>{(l) => (needsTap ? STRINGS[l].hearIt : speaking ? STRINGS[l].orb.speaking : STRINGS[l].hearAgain)}</SameSize>
        </button>
        <button className="patient-ok" onClick={onDismiss}>
          <SameSize lang={lang}>{(l) => STRINGS[l].ok}</SameSize>
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
  return (
    <div className="patient-card patient-care-told" role="status">
      <p className="patient-card-title">
        <SameSize lang={lang}>{(l) => STRINGS[l].careToldTitle}</SameSize>
      </p>
      <p className="patient-card-detail">
        <SameSize lang={lang}>{(l) => STRINGS[l].careToldDetail}</SameSize>
      </p>
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

  const from = message.from_name;
  return (
    <div className="patient-card patient-message">
      <Orb mode={playing ? "speaking" : "idle"} onClick={toggle} tabIndex={-1} aria-hidden />
      <div className="patient-message-copy">
        <p className="patient-card-title">
          <SameSize lang={lang}>{(l) => STRINGS[l].messageTitle(from)}</SameSize>
        </p>
        {playing ? (
          <Pages
            key={message.id}
            className="patient-card-detail"
            text={`"${message.text}"`}
            progress={() => {
              const audio = audioRef.current;
              return audio?.duration ? audio.currentTime / audio.duration : 0;
            }}
          />
        ) : (
          <p className="patient-card-detail">
            <SameSize lang={lang}>{(l) => STRINGS[l].messageVoice(from)}</SameSize>
          </p>
        )}
      </div>
      <button className="patient-play" onClick={toggle}>
        <SameSize lang={lang}>{(l) => (playing ? STRINGS[l].stop : STRINGS[l].play)}</SameSize>
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
