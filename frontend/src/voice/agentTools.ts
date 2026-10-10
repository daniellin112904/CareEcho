import { getFacts, logInteraction, logStatement, raiseAlert, type StatementKind } from "../api";

const KINDS: StatementKind[] = ["medication", "meal", "activity", "feeling", "other"];

// Said to the agent when the backend can't be reached, so it falls back to "I'm not sure"
// instead of answering from nothing
const LOOKUP_FAILED = "NO_MEMORY: the memory list couldn't be loaded. Say you are not sure right now.";

// An answer that promises to find out. If the agent says this without calling ask_caregiver,
// the alert is raised anyway, so a promise made to the patient is always passed on.
const PROMISED_TO_ASK = /\b(not sure|don['’]t know|do not know|i['’]ll ask|i will ask|find out|ask the care team)\b/i;

type Turn = {
  question: string;
  answer: string[];
  topic: string;
  memoryIds: string[];
  lookedUp: boolean;
  askedCaregiver: boolean;
};

/**
 * One conversation's client tools (defined in backend/app/voice/agent.py) plus the record
 * of what was asked and answered. Create a fresh one per conversation.
 *
 * Questions and answers are logged here, from the transcript, not by the AI: a test
 * showed the agent batching its log calls at the end of the conversation. Each turn
 * remembers which memories its lookups returned, so the record of what an answer was
 * based on never depends on the AI copying IDs correctly.
 */
export function createAgentSession(patientName: string) {
  let turn: Turn | null = null;

  // A turn is logged once the next question starts (or the conversation ends), so the
  // whole answer and any "I'll ask the care team" are known by then
  function flush() {
    if (turn && !turn.askedCaregiver && PROMISED_TO_ASK.test(turn.answer.join(" "))) {
      turn.askedCaregiver = true;
      raiseAlert("missing_info", `${patientName} asked: "${turn.question}"`).catch((err) =>
        console.warn("Backup alert failed", err),
      );
    }
    if (turn?.lookedUp && turn.answer.length > 0) {
      logInteraction({
        topic: turn.topic,
        question: turn.question,
        answer: turn.answer.join(" "),
        memory_ids: turn.memoryIds,
        answered: !turn.askedCaregiver,
      }).catch((err) => console.warn("Logging the answer failed", err));
    }
    turn = null;
  }

  function onMessage(role: "user" | "agent", message: string) {
    const text = message.trim();
    // Silence comes through as "..."
    if (!text || /^\.+$/.test(text)) return;
    if (role === "user") {
      flush();
      turn = { question: text, answer: [], topic: "", memoryIds: [], lookedUp: false, askedCaregiver: false };
    } else {
      turn?.answer.push(text);
    }
  }

  const clientTools = {
    async get_memories({ topic }: { topic?: string }) {
      try {
        const { facts, memory_ids } = await getFacts();
        if (turn) {
          turn.lookedUp = true;
          turn.topic ||= topic ?? "";
          turn.memoryIds = [...new Set([...turn.memoryIds, ...memory_ids])];
        }
        return facts;
      } catch (err) {
        console.warn("get_memories failed", err);
        return LOOKUP_FAILED;
      }
    },

    async ask_caregiver({ question }: { question?: string }) {
      if (turn) turn.askedCaregiver = true;
      try {
        await raiseAlert("missing_info", `${patientName} asked: "${question ?? turn?.question ?? ""}"`);
        return "The care team has the question. Tell them you'll find out for them.";
      } catch (err) {
        console.warn("ask_caregiver failed", err);
        return "The care team couldn't be reached right now. Say you'll ask them later.";
      }
    },

    async log_patient_statement({ text, kind }: { text?: string; kind?: string }) {
      const safeKind = KINDS.includes(kind as StatementKind) ? (kind as StatementKind) : "other";
      try {
        await logStatement(text ?? "", safeKind);
      } catch (err) {
        console.warn("log_patient_statement failed", err);
      }
      return "Saved as something they said, not as a confirmed fact.";
    },
  };

  return { clientTools, onMessage, flush };
}
