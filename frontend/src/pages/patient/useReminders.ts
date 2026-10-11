import { useCallback, useEffect, useRef, useState } from "react";
import { getUpcomingReminders, reminderAudioUrl, type Reminder } from "../../api";
import { chime } from "../../voice/chime";

const PLAYED_KEY = "vela.playedReminders";
// The reminder card stays up this long after it's spoken, so it can be read again
const SHOW_FOR_MS = 3 * 60_000;

function loadPlayed(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(PLAYED_KEY) ?? "[]") as string[]);
  } catch {
    return new Set();
  }
}

function savePlayed(played: Set<string>) {
  try {
    localStorage.setItem(PLAYED_KEY, JSON.stringify([...played].slice(-50)));
  } catch {
    // Without storage a reminder may repeat after a reload, which is harmless
  }
}

/**
 * Speaks each reminder once, when it's due. While the patient is talking to Vela (busy),
 * a due reminder waits, so it never talks over a conversation.
 */
export function useReminders(busy: boolean) {
  const [upcoming, setUpcoming] = useState<Reminder[]>([]);
  const [current, setCurrent] = useState<Reminder | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [needsTap, setNeedsTap] = useState(false);
  const played = useRef(loadPlayed());
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    const load = () =>
      getUpcomingReminders()
        .then((data) => setUpcoming(data.reminders))
        .catch(() => {});
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, []);

  const speak = useCallback((reminder: Reminder) => {
    audioRef.current?.pause();
    const audio = new Audio(reminderAudioUrl(reminder.id));
    audio.onplay = () => {
      setSpeaking(true);
      setNeedsTap(false);
    };
    audio.onpause = () => setSpeaking(false);
    audio.onerror = () => setSpeaking(false);
    audioRef.current = audio;
    // Browsers block sound until someone has touched the page; then the card offers a button
    audio.play().catch(() => setNeedsTap(true));
  }, []);

  // Every few seconds: is a reminder due that hasn't been spoken yet?
  useEffect(() => {
    if (busy) return;
    const check = () => {
      const now = Date.now();
      const due = upcoming.find((r) => Date.parse(r.at) <= now && !played.current.has(r.id));
      if (!due) return;
      played.current.add(due.id);
      savePlayed(played.current);
      setCurrent(due);
      chime("gentle");
      setTimeout(() => speak(due), 1_200);
    };
    check();
    const id = setInterval(check, 5_000);
    return () => clearInterval(id);
  }, [busy, upcoming, speak]);

  // A conversation starting stops the reminder, so only one voice ever plays
  useEffect(() => {
    if (busy) audioRef.current?.pause();
  }, [busy]);

  useEffect(() => {
    if (!current || speaking) return;
    const id = setTimeout(() => setCurrent(null), SHOW_FOR_MS);
    return () => clearTimeout(id);
  }, [current, speaking]);

  useEffect(() => () => audioRef.current?.pause(), []);

  const dismiss = useCallback(() => {
    audioRef.current?.pause();
    setCurrent(null);
    setNeedsTap(false);
  }, []);

  return {
    reminder: current,
    speaking,
    needsTap,
    /** How far the reminder audio has got, from 0 to 1 */
    progress: () => {
      const audio = audioRef.current;
      return audio?.duration ? audio.currentTime / audio.duration : 0;
    },
    replay: () => current && speak(current),
    dismiss,
  };
}
