const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const PIN_KEY = "vela.staffPin";

export type Memory = {
  id: string;
  kind: string;
  summary: string;
  details: Record<string, unknown> | null;
  event_at: string | null;
  /** A day with no time ("Anna might visit Saturday"): event_at is that day's midnight */
  all_day?: boolean;
  status: string;
  source: string;
  source_quote: string | null;
  certainty?: Certainty | null;
  confirmed_at?: string | null;
  /** For an update: the memory it replaces (or replaced, once confirmed) */
  supersedes_id?: string | null;
  /** The caregiver session it was extracted from */
  session_id?: string | null;
};

export type Certainty = "definite" | "tentative";

export type Voice = { voice_id: string; name: string };

export type FamilyMessage = {
  id: string;
  from_name: string;
  voice_id: string;
  text: string;
  created_at: string;
};

export type VoiceSession = {
  token: string;
  dynamic_variables: Record<string, string>;
};

export const staffPin = {
  get: () => sessionStorage.getItem(PIN_KEY),
  set: (pin: string) => sessionStorage.setItem(PIN_KEY, pin),
  clear: () => sessionStorage.removeItem(PIN_KEY),
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (typeof options.body === "string") headers.set("Content-Type", "application/json");
  const pin = staffPin.get();
  if (pin && !headers.has("X-Staff-Pin")) headers.set("X-Staff-Pin", pin);

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `${res.status} ${res.statusText}`);
  }
  return (res.status === 204 ? undefined : res.json()) as Promise<T>;
}

export function getCurrentMemories(topic?: string) {
  const query = topic ? `?topic=${encodeURIComponent(topic)}` : "";
  return request<{ memories: Memory[] }>(`/memories/current${query}`);
}

// Caregiver memories (staff): extraction and review. Nothing pending is ever spoken; a memory
// reaches the patient only once staff confirm it. See docs/memory-track.md, "API for the
// Interface owner". Error messages (409 and 503 especially) are written to be shown as they are.

/** A memory waiting for staff, with what to check before confirming it */
export type PendingMemory = Memory & {
  /** What extraction flagged for a person to check, like "No day was said..." */
  warnings: string[];
  /** For an update: the current memory it would replace */
  replaces: Pick<Memory, "id" | "summary" | "event_at" | "all_day" | "details" | "status"> | null;
  /** The memory it replaces was already changed or cancelled: it can only be rejected */
  stale: boolean;
};

export type ExtractionResult = {
  session_id: string;
  /** The new pending memories, each with its warnings */
  candidates: (Memory & { warnings: string[] })[];
  /** What was left out on purpose, and why ("medicine is never saved as a memory") */
  dropped: { summary: string | null; reason: string }[];
};

/** What a caregiver said, turned into pending memories (takes a few seconds: Gemini) */
export function submitTranscript(transcript: string) {
  return request<ExtractionResult>("/sessions/transcript", {
    method: "POST",
    body: JSON.stringify({ transcript, source: "caregiver_typed" }),
  });
}

export function listPendingMemories() {
  return request<{ pending: PendingMemory[] }>("/memories/pending");
}

/** From now on Vela may say it. Pass a certainty only to change what extraction proposed. */
export function confirmMemory(id: string, certainty?: Certainty) {
  return request<Memory>(`/memories/${id}/confirm`, {
    method: "POST",
    body: JSON.stringify(certainty ? { certainty } : {}),
  });
}

/** A pending memory was wrong: it's kept as rejected and never spoken */
export function rejectMemory(id: string) {
  return request<Memory>(`/memories/${id}/reject`, { method: "POST" });
}

/** A current plan was cancelled: kept for receipts of past answers, never spoken again */
export function cancelMemory(id: string) {
  return request<Memory>(`/memories/${id}/cancel`, { method: "POST" });
}

export function startVoiceSession() {
  return request<VoiceSession>("/voice/session");
}

export function verifyStaffPin(pin: string) {
  return request<void>("/staff/verify", { method: "POST", headers: { "X-Staff-Pin": pin } });
}

export function listVoices() {
  return request<{ voices: Voice[] }>("/voice/voices");
}

export function cloneVoice(name: string, audio: Blob, filename: string) {
  const form = new FormData();
  form.append("name", name);
  form.append("file", audio, filename);
  return request<Voice>("/voice/voices", { method: "POST", body: form });
}

export function deleteVoice(voiceId: string) {
  return request<void>(`/voice/voices/${voiceId}`, { method: "DELETE" });
}

export function listFamilyMessages() {
  return request<{ messages: FamilyMessage[] }>("/family-messages");
}

export function createFamilyMessage(voiceId: string, text: string) {
  return request<FamilyMessage>("/family-messages", {
    method: "POST",
    body: JSON.stringify({ voice_id: voiceId, text }),
  });
}

export function deleteFamilyMessage(id: string) {
  return request<void>(`/family-messages/${id}`, { method: "DELETE" });
}

export function getLatestFamilyMessage() {
  return request<{ message: Omit<FamilyMessage, "voice_id"> | null }>("/family-messages/latest");
}

export function familyMessageAudioUrl(id: string) {
  return `${API_URL}/family-messages/${id}/audio`;
}

// Voice agent tools (patient side, no PIN)

export type AlertKind = "missing_info" | "self_reported_med" | "help_requested";
export type StatementKind = "medication" | "meal" | "activity" | "feeling" | "other";

export type Alert = {
  id: string;
  ts: string;
  kind: AlertKind;
  message: string;
  resolved: boolean;
};

export function getFacts() {
  return request<{ facts: string; memory_ids: string[] }>("/voice/facts");
}

export function raiseAlert(kind: AlertKind, message: string) {
  return request<Alert>("/alerts", { method: "POST", body: JSON.stringify({ kind, message }) });
}

export function logStatement(text: string, kind: StatementKind) {
  return request<unknown>("/patient/statements", { method: "POST", body: JSON.stringify({ text, kind }) });
}

export function logInteraction(interaction: {
  conversation_id: string | null;
  topic: string;
  question: string;
  answer: string;
  memory_ids: string[];
  answered: boolean;
}) {
  return request<unknown>("/interactions", { method: "POST", body: JSON.stringify(interaction) });
}

// Alerts (staff)

export function listAlerts() {
  return request<{ alerts: Alert[] }>("/alerts");
}

export function resolveAlert(id: string) {
  return request<void>(`/alerts/${id}/resolve`, { method: "POST" });
}

export function getAlertStatus(id: string) {
  return request<{ resolved: boolean }>(`/alerts/${id}/status`);
}

// Answer receipts (staff)

export type MemorySource = {
  id: string;
  summary: string;
  status: string;
  source: string;
  source_quote: string | null;
  event_at: string | null;
  confirmed_at: string | null;
};

export type Interaction = {
  id: string;
  ts: string;
  conversation_id: string | null;
  topic: string;
  question: string;
  answer: string;
  answered: boolean;
  /** The memories the answer used */
  sources: MemorySource[];
  /** How many memories the agent looked at */
  checked: number;
};

export function listInteractions() {
  return request<{ interactions: Interaction[] }>("/interactions");
}

// Reminders

export type Reminder = { id: string; at: string; text: string; memory_id: string };

export function getUpcomingReminders() {
  return request<{ reminders: Reminder[] }>("/reminders/upcoming");
}

export function reminderAudioUrl(id: string) {
  return `${API_URL}/reminders/${id}/audio`;
}

export function sendReminderNow(memoryId: string) {
  return request<Reminder>("/reminders/now", { method: "POST", body: JSON.stringify({ memory_id: memoryId }) });
}
