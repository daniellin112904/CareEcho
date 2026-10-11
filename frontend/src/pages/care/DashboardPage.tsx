import { useEffect, useState } from "react";
import { getDashboard, type AlertKind, type Dashboard } from "../../api";
import { KIND_LABEL } from "./alertFeed";

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = () =>
      getDashboard()
        .then((d) => {
          setData(d);
          setError("");
        })
        .catch((err: Error) => setError(err.message));
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  const top = data?.by_topic[0];
  const peak = Math.max(1, ...(data?.by_hour.map((h) => h.asks) ?? []));
  const alerts = Object.entries(data?.open_alerts ?? {}).filter(([, n]) => n) as [AlertKind, number][];

  return (
    <>
      <section className="care-section">
        <h1>Today</h1>
        {error && <p className="care-error">{error}</p>}
        {data && (
          <p className="care-lede dash-headline">
            {top
              ? `Asked about most today: ${top.topic}, ${times(top.asks)}.`
              : `The patient hasn't asked Vela anything yet today.`}{" "}
            {data.asks_today} {data.asks_today === 1 ? "question" : "questions"} in all.
          </p>
        )}
      </section>

      {data && (
        <>
          <section className="care-section">
            <h2>Questions, last 24 hours</h2>
            <div className="dash-chart" role="img" aria-label="Questions asked each hour over the last 24 hours">
              {data.by_hour.map((h) => (
                <div key={h.hour} className="dash-col" title={`${hourWords(h.hour)}: ${h.asks} ${h.asks === 1 ? "question" : "questions"}`}>
                  <div className="dash-bar" style={{ height: `${(h.asks / peak) * 100}%` }} />
                </div>
              ))}
            </div>
            <div className="dash-axis memory-when">
              <span>{hourWords(data.by_hour[0]?.hour)}</span>
              <span>Now</span>
            </div>
          </section>

          <section className="care-section">
            <h2>By topic</h2>
            {data.by_topic.length === 0 ? (
              <p className="care-notice">No questions yet today.</p>
            ) : (
              <ul className="memory-list">
                {data.by_topic.map((t) => (
                  <li key={t.topic} className="memory-row">
                    <span className="memory-summary">{t.topic}</span>
                    <span className="memory-when">{times(t.asks)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="care-section">
            <h2>Open alerts</h2>
            {alerts.length === 0 ? (
              <p className="care-notice">No open alerts.</p>
            ) : (
              <ul className="memory-list">
                {alerts.map(([kind, n]) => (
                  <li key={kind} className="memory-row">
                    <span className="alert-kind" data-kind={kind}>
                      {KIND_LABEL[kind]}
                    </span>
                    <span className="memory-summary">{n} open</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="care-section">
            <h2>What the patient said they did</h2>
            <p className="care-lede">In the patient's own words. Not verified.</p>
            {data.self_reported_today.length === 0 ? (
              <p className="care-notice">Nothing yet today.</p>
            ) : (
              <ul className="memory-list">
                {data.self_reported_today.map((s) => (
                  <li key={s.id} className="memory-row">
                    <span className="memory-summary">"{s.text}"</span>
                    <span className="memory-when">{new Date(s.ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>
                    <span className="memory-status" data-status="pending">
                      Not verified
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </>
  );
}

function times(n: number) {
  return n === 1 ? "once" : `${n} times`;
}

function hourWords(iso?: string) {
  return iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric" }) : "";
}
