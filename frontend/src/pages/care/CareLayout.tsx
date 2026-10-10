import { useEffect, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { staffPin, verifyStaffPin, type Alert } from "../../api";
import Orb from "../../voice/Orb";
import { KIND_LABEL, useAlertFeed } from "./alertFeed";
import "./care.css";

export default function CareLayout() {
  const [unlocked, setUnlocked] = useState(() => staffPin.get() !== null);

  if (!unlocked) return <PinGate onUnlock={() => setUnlocked(true)} />;

  return (
    <StaffShell
      onLock={() => {
        staffPin.clear();
        setUnlocked(false);
      }}
    />
  );
}

function StaffShell({ onLock }: { onLock: () => void }) {
  const { feed, toasts, dismiss, openCount } = useAlertFeed();
  const [permission, setPermission] = useState(() => ("Notification" in window ? Notification.permission : "denied"));

  // "(2) Vela" in the browser tab, so open alerts show even from another tab
  useEffect(() => {
    const base = document.title.replace(/^\(\d+\) /, "");
    document.title = openCount > 0 ? `(${openCount}) ${base}` : base;
    return () => {
      document.title = base;
    };
  }, [openCount]);

  async function enableNotifications() {
    setPermission(await Notification.requestPermission());
  }

  return (
    <div className="care">
      <header className="care-bar">
        <span className="care-mark">Vela</span>
        <nav className="care-nav">
          <NavLink to="voices">Family messages</NavLink>
          <NavLink to="memories">Memories</NavLink>
          <NavLink to="conversations">Conversations</NavLink>
          <NavLink to="alerts">
            Alerts
            {openCount > 0 && (
              <span className="nav-badge" aria-label={`${openCount} open`}>
                {openCount}
              </span>
            )}
          </NavLink>
        </nav>
        <div className="care-bar-actions">
          {permission === "default" && (
            <button className="care-secondary" onClick={enableNotifications}>
              Turn on notifications
            </button>
          )}
          <Link className="care-secondary" to="/patient" onClick={staffPin.clear}>
            Lock and open patient screen
          </Link>
          <button className="care-secondary" onClick={onLock}>
            Lock
          </button>
        </div>
      </header>
      <main className="care-main">
        <Outlet context={feed} />
      </main>
      <div className="toast-stack" aria-live="assertive">
        {toasts.map((alert) => (
          <Toast key={alert.id} alert={alert} onDismiss={dismiss} />
        ))}
      </div>
    </div>
  );
}

function Toast({ alert, onDismiss }: { alert: Alert; onDismiss: (id: string) => void }) {
  // A request for help stays until someone acts on it; the others fade after 15 seconds
  useEffect(() => {
    if (alert.kind === "help_requested") return;
    const timer = setTimeout(() => onDismiss(alert.id), 15_000);
    return () => clearTimeout(timer);
  }, [alert.id, alert.kind, onDismiss]);

  return (
    <div className="toast" data-kind={alert.kind} role="alert">
      <div className="alert-head">
        <span className="alert-kind" data-kind={alert.kind}>
          {KIND_LABEL[alert.kind]}
        </span>
        <span className="memory-when">Just now</span>
      </div>
      <p className="toast-message">{alert.message}</p>
      <div className="toast-actions">
        <Link className="care-secondary" to="alerts" onClick={() => onDismiss(alert.id)}>
          View alerts
        </Link>
        <button className="care-quiet" onClick={() => onDismiss(alert.id)}>
          Dismiss
        </button>
      </div>
    </div>
  );
}

function PinGate({ onUnlock }: { onUnlock: () => void }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setChecking(true);
    setError("");
    try {
      await verifyStaffPin(pin);
      staffPin.set(pin);
      onUnlock();
    } catch (err) {
      const wrongPin = err instanceof Error && err.message === "Wrong staff PIN";
      setError(wrongPin ? "That PIN didn't match. Try again." : "Can't reach the Vela server. Check that the backend is running.");
      setPin("");
    } finally {
      setChecking(false);
    }
  }

  return (
    <main className="pin-gate">
      <form className="pin-form" onSubmit={submit}>
        <Orb palette="teal" tabIndex={-1} aria-hidden />
        <h1>Staff access</h1>
        <label htmlFor="pin">Enter the staff PIN</label>
        <input
          id="pin"
          className="pin-input"
          type="password"
          inputMode="numeric"
          autoComplete="off"
          autoFocus
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
        />
        {error && <p className="care-error">{error}</p>}
        <button className="care-primary" disabled={!pin || checking}>
          {checking ? "Checking" : "Unlock"}
        </button>
      </form>
    </main>
  );
}
