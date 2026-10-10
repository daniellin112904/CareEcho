const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const PIN_KEY = "vela.staffPin";

export type Memory = {
  id: string;
  kind: string;
  summary: string;
  details: Record<string, unknown> | null;
  event_at: string | null;
  status: string;
  source: string;
  source_quote: string | null;
};

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
