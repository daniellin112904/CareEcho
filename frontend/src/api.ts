const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export function getCurrentMemories(topic?: string) {
  const query = topic ? `?topic=${encodeURIComponent(topic)}` : "";
  return request<{ memories: Memory[] }>(`/memories/current${query}`);
}