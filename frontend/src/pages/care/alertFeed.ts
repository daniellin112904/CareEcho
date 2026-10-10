import { useCallback, useEffect, useRef, useState } from "react";
import { listAlerts, type Alert, type AlertKind } from "../../api";
import { chime } from "../../voice/chime";

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
        chime(fresh.some((a) => a.kind === "help_requested") ? "urgent" : "alert");
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

function notifyDesktop(alerts: Alert[]) {
  if (!("Notification" in window) || Notification.permission !== "granted" || !document.hidden) return;
  for (const alert of alerts) {
    const note = new Notification(`Vela: ${KIND_LABEL[alert.kind]}`, { body: alert.message, tag: alert.id });
    note.onclick = () => window.focus();
  }
}
