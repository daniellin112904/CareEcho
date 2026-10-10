import { getFacts, logInteraction, logStatement, raiseAlert, type StatementKind } from "../api";

const KINDS: StatementKind[] = ["medication", "meal", "activity", "feeling", "other"];

// Said to the agent when the backend can't be reached, so it falls back to "I'm not sure"
// instead of answering from nothing
const LOOKUP_FAILED = "NO_MEMORY: the memory list couldn't be loaded. Say you are not sure right now.";

// An answer that promises to find out. If the agent says this without calling ask_caregiver,
// the alert is raised anyway, so a promise made to the patient is always passed on.
const PROMISED_TO_ASK =
  /\b(not sure|don['’]t know|do not know|i['’]ll ask|i will ask|find out|ask(ed)? (the|your) care team)\b/i;

// Backup for emergencies: if the patient says one of these, the urgent alert goes out from
// the page itself, even if the agent misses it. Phrases, not single words, so "help me
// remember" or "a fall concert" don't set it off.
const EMERGENCY =
  /\b(i fell|i['’]ve fallen|i have fallen|fell down|can['’]?not get up|can['’]t get up|chest pain|my chest hurts|can['’]t breathe|cannot breathe|hard to breathe|i['’]m bleeding|i am bleeding|i['’]m hurt|i am hurt|hurt myself|i['’]m lost|i am lost|heart attack|call (an )?ambulance|call 911)\b/i;

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
type SessionHooks = {
  /** An urgent alert went out; the patient screen shows "Your care team has been told". */
  onUrgentAlert: (alertId: string) => void;
  /** Background note for the agent; it doesn't reply to these. */
  tellAgent: (text: string) => void;
};

export function createAgentSession(patientName: string, hooks: SessionHooks) {
  let turn: Turn | null = null;
  // ElevenLabs' ID for this conversation, so the staff page can group its answers
  let conversationId: string | null = null;
  // One urgent alert per thing the patient says, whether the agent or the backup raised it.
  // A new symptom later ("my chest hurts too") is a new alert, so staff see it get worse.
  let urgent: Promise<string | null> | null = null;

  function raiseUrgent(words: string) {
    urgent ??= raiseAlert("help_requested", `${patientName} may need help. They said: "${words}"`)
      .then((alert) => {
        hooks.onUrgentAlert(alert.id);
        return alert.id;
      })
      .catch((err) => {
        console.warn("Urgent alert failed", err);
        urgent = null;
        return null;
      });
    return urgent;
  }

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
        conversation_id: conversationId,
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
      urgent = null;
      if (EMERGENCY.test(text)) {
        raiseUrgent(text).then((id) => {
          if (id) hooks.tellAgent(`The care team has just been alerted that ${patientName} may need help.`);
        });
      }
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

    async raise_urgent_alert({ reason }: { reason?: string }) {
      const id = await raiseUrgent(reason ?? turn?.question ?? "");
      return id
        ? "The care team has been alerted. Calmly tell them you've told their care team right away."
        : "The alert could not be sent. Calmly tell them to call 911 or get someone nearby if they can.";
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

  function setConversationId(id: string) {
    conversationId = id;
  }

  return { clientTools, onMessage, flush, setConversationId };
}
