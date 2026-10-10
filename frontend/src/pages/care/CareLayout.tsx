import { useState, type FormEvent } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { staffPin, verifyStaffPin } from "../../api";
import "./care.css";

export default function CareLayout() {
  const [unlocked, setUnlocked] = useState(() => staffPin.get() !== null);

  if (!unlocked) return <PinGate onUnlock={() => setUnlocked(true)} />;

  function lock() {
    staffPin.clear();
    setUnlocked(false);
  }

  return (
    <div className="care">
      <header className="care-bar">
        <span className="care-mark">Vela</span>
        <nav className="care-nav">
          <NavLink to="voices">Family messages</NavLink>
          <NavLink to="memories">Memories</NavLink>
          <NavLink to="alerts">Alerts</NavLink>
        </nav>
        <Link className="care-quiet" to="/patient" onClick={staffPin.clear}>
          Lock and open patient screen
        </Link>
        <button className="care-quiet" onClick={lock}>
          Lock
        </button>
      </header>
      <main className="care-main">
        <Outlet />
      </main>
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
