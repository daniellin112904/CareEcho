import { useCallback, useEffect, useRef, useState } from "react";
import { listAlerts, type Alert, type AlertKind } from "../../api";

export const KIND_LABEL: Record<AlertKind, string> = {
  missing_info: "Needs an answer",
  self_reported_med: "Medicine, not verified",
  help_requested: "Asked for help",
};

export type AlertFeed = {
  alerts: Alert[] | null;
  error: string;
  refresh: () => void;
};

/**
 * Checks for alerts every 5 seconds on every staff page, and announces new ones with a
 * toast, a chime, and (when the tab is in the background) a desktop notification.
 * Alerts that already existed when the page opened are listed but not announced.
 */
export function useAlertFeed() {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [error, setError] = useState("");
  const [toasts, setToasts] = useState<Alert[]>([]);
  const seen = useRef<Set<string> | null>(null);

  const refresh = useCallback(() => {
    listAlerts()
      .then((data) => {
        setAlerts(data.alerts);
        setError("");
        if (seen.current === null) {
          seen.current = new Set(data.alerts.map((a) => a.id));
          return;
        }
        const fresh = data.alerts.filter((a) => !a.resolved && !seen.current!.has(a.id));
        if (fresh.length === 0) return;
        fresh.forEach((a) => seen.current!.add(a.id));
        setToasts((current) => [...fresh, ...current].slice(0, 3));
        chime(fresh.some((a) => a.kind === "help_requested"));
        notifyDesktop(fresh);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5_000);
    return () => clearInterval(id);
  }, [refresh]);

  const dismiss = useCallback((id: string) => setToasts((current) => current.filter((t) => t.id !== id)), []);

  // A toast disappears once its alert is resolved, from any page
  const openIds = new Set(alerts?.filter((a) => !a.resolved).map((a) => a.id));
  const visibleToasts = toasts.filter((t) => openIds.has(t.id));

  return { feed: { alerts, error, refresh } satisfies AlertFeed, toasts: visibleToasts, dismiss, openCount: openIds.size };
}

let audio: AudioContext | null = null;

/** A soft two-note chime, generated in the browser so there's no sound file to load. */
function chime(urgent: boolean) {
  try {
    audio ??= new AudioContext();
    void audio.resume();
    const notes = urgent ? [880, 660, 880, 660] : [660, 880];
    notes.forEach((frequency, i) => {
      const start = audio!.currentTime + i * 0.18;
      const tone = audio!.createOscillator();
      const volume = audio!.createGain();
      tone.frequency.value = frequency;
      volume.gain.setValueAtTime(0, start);
      volume.gain.linearRampToValueAtTime(0.15, start + 0.02);
      volume.gain.exponentialRampToValueAtTime(0.001, start + 0.5);
      tone.connect(volume).connect(audio!.destination);
      tone.start(start);
      tone.stop(start + 0.5);
    });
  } catch {
    // No sound is fine: the toast and badge still show
  }
}

function notifyDesktop(alerts: Alert[]) {
  if (!("Notification" in window) || Notification.permission !== "granted" || !document.hidden) return;
  for (const alert of alerts) {
    const note = new Notification(`Vela: ${KIND_LABEL[alert.kind]}`, { body: alert.message, tag: alert.id });
    note.onclick = () => window.focus();
  }
}
