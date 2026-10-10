import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { resolveAlert, type Alert } from "../../api";
import { KIND_LABEL, type AlertFeed } from "./alertFeed";

export default function AlertsPage() {
  // Shared with the badge and notifications in CareLayout, so they stay in sync
  const { alerts, error: loadError, refresh } = useOutletContext<AlertFeed>();
  const [actionError, setActionError] = useState("");
  const error = actionError || loadError;

  async function resolve(alert: Alert) {
    try {
      await resolveAlert(alert.id);
      setActionError("");
      refresh();
    } catch (err) {
      setActionError((err as Error).message);
    }
  }

  const open = alerts?.filter((a) => !a.resolved) ?? [];
  const done = alerts?.filter((a) => a.resolved) ?? [];

  return (
    <>
      <section className="care-section">
        <h1>Alerts</h1>
        <p className="care-lede">
          When the patient asks something Vela can't answer, mentions taking medicine, or asks for help, it shows up
          here.
        </p>
        {error && <p className="care-error">{error}</p>}
        {alerts && open.length === 0 && <p className="care-notice">No open alerts. New ones appear here on their own.</p>}
        {open.length > 0 && <AlertList alerts={open} onResolve={resolve} />}
      </section>

      {done.length > 0 && (
        <section className="care-section">
          <h2>Resolved</h2>
          <AlertList alerts={done} />
        </section>
      )}
    </>
  );
}

function AlertList({ alerts, onResolve }: { alerts: Alert[]; onResolve?: (alert: Alert) => void }) {
  return (
    <ul className="memory-list">
      {alerts.map((alert) => (
        <li key={alert.id} className="alert-row" data-resolved={alert.resolved}>
          <div className="alert-head">
            <span className="alert-kind" data-kind={alert.kind}>
              {KIND_LABEL[alert.kind]}
            </span>
            <span className="memory-when">
              {new Date(alert.ts).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })}
            </span>
          </div>
          <p className="alert-message">{alert.message}</p>
          {onResolve && (
            <button className="care-secondary" onClick={() => onResolve(alert)}>
              Mark resolved
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
