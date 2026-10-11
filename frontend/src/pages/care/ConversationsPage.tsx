import { useEffect, useState } from "react";
import { listInteractions, type Interaction, type MemorySource } from "../../api";

const SOURCE_LABEL: Record<string, string> = {
  caregiver_session: "Said by a caregiver in a listening session",
  caregiver_typed: "Typed by a caregiver",
  patient: "Said by the patient, not verified",
};

// Answers from Vela's other tools: their topic is set in frontend/src/voice/agentTools.ts
const TOOL_SOURCE: Record<string, string> = {
  "Life story": "From the life story",
  "Family messages": "From a family message",
};

export default function ConversationsPage() {
  const [interactions, setInteractions] = useState<Interaction[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = () =>
      listInteractions()
        .then((data) => {
          setInteractions(data.interactions);
          setError("");
        })
        .catch((err: Error) => setError(err.message));
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  const conversations = groupByConversation(interactions ?? []);

  return (
    <section className="care-section">
      <h1>Conversations</h1>
      <p className="care-lede">
        Every answer Vela gave about plans and people, with a receipt: the confirmed memory it came from, in the
        caregiver's own words. Open a receipt to see who said it and when it was confirmed.
      </p>
      {error && <p className="care-error">{error}</p>}
      {interactions && conversations.length === 0 && (
        <p className="care-notice">No answers yet. They appear here after the patient asks Vela about their plans.</p>
      )}
      {conversations.map((answers) => (
        <div key={answers[0].conversation_id ?? answers[0].id} className="conversation">
          <p className="conversation-head">
            {/* Answers logged before conversation IDs were recorded can't be grouped */}
            {answers[0].conversation_id ? "Conversation" : "Earlier answers"} · {formatWhen(answers[0].ts)} ·{" "}
            {answers.length} {answers.length === 1 ? "answer" : "answers"}
          </p>
          <ul className="memory-list">
            {answers.map((answer) => (
              <li key={answer.id} className="qa-row">
                <p className="qa-line">
                  <span className="qa-who">Patient</span>
                  {answer.question}
                </p>
                <p className="qa-line qa-answer">
                  <span className="qa-who">Vela</span>
                  {answer.answer}
                </p>
                <Receipt answer={answer} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function Receipt({ answer }: { answer: Interaction }) {
  const checked = `Checked ${answer.checked} ${answer.checked === 1 ? "memory" : "memories"}`;

  // Part of an answer can come from memory while the rest went to the care team
  return (
    <div className="receipts">
      {answer.sources.map((source) => (
        // When the care team was asked, a matched memory may be only related, not what the answer was based on
        <SourceReceipt key={source.id} source={source} label={answer.answered ? "Based on" : "Related"} />
      ))}
      {!answer.answered && <span className="alert-kind">Not in memory · care team asked</span>}
      {answer.sources.length === 0 && (
        <span className="memory-when">
          {!answer.answered
            ? checked
            : (TOOL_SOURCE[answer.topic] ??
              (answer.checked === 0 ? "Not from a memory" : `${checked}, none used in the answer`))}
        </span>
      )}
    </div>
  );
}

function SourceReceipt({ source, label }: { source: MemorySource; label: string }) {
  return (
    <details className="receipt">
      <summary>
        <span className="receipt-label">{label}</span>
        <span className="receipt-summary">{source.summary}</span>
        <span className="memory-status" data-status={source.status}>
          {source.status}
        </span>
      </summary>
      <div className="receipt-body">
        {source.source_quote && <blockquote className="receipt-quote">"{source.source_quote}"</blockquote>}
        <p className="memory-when">
          {SOURCE_LABEL[source.source] ?? source.source}
          {source.confirmed_at && ` · confirmed ${formatWhen(source.confirmed_at)}`}
        </p>
      </div>
    </details>
  );
}

/** Newest conversation first; answers inside a conversation in the order they were given. */
function groupByConversation(interactions: Interaction[]) {
  const groups = new Map<string, Interaction[]>();
  for (const row of interactions) {
    const key = row.conversation_id ?? "earlier";
    groups.set(key, [row, ...(groups.get(key) ?? [])]);
  }
  return [...groups.values()];
}

function formatWhen(iso: string) {
  return new Date(iso).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });
}
