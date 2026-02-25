import type {
  LLMRequest,
  LLMRequestSummary,
  RawCapture,
  SessionStats,
  SessionSummary,
} from "../types";

// ---------------------------------------------------------------------------
// Session detail combines Session fields with stats
// ---------------------------------------------------------------------------

export interface SessionDetail {
  id: string;
  name: string;
  started_at: string;
  ended_at: string | null;
  request_count: number;
  total_tokens: number;
  estimated_cost_usd: number;
  stats: SessionStats;
}

// ---------------------------------------------------------------------------
// Fetch wrapper
// ---------------------------------------------------------------------------

const BASE_URL = "/api";

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// API namespace
// ---------------------------------------------------------------------------

export interface ProviderMeta {
  name: string;
  display_name: string;
  color: string;
}

export const api = {
  sessions: {
    list: () => fetchJSON<SessionSummary[]>("/sessions"),
    get: (id: string) => fetchJSON<SessionDetail>(`/sessions/${id}`),
    createNew: (name?: string) =>
      fetchJSON<SessionDetail>("/sessions/new", {
        method: "POST",
        body: name ? JSON.stringify({ name }) : undefined,
      }),
    rename: (id: string, name: string) =>
      fetchJSON<SessionDetail>(`/sessions/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      }),
    delete: (id: string) =>
      fetch(`${BASE_URL}/sessions/${id}`, { method: "DELETE" }),
    deleteAll: () =>
      fetch(`${BASE_URL}/sessions`, { method: "DELETE" }),
    exportUrl: (id: string, format: "json" | "markdown" | "csv") =>
      `${BASE_URL}/sessions/${id}/export?format=${format}`,
  },

  requests: {
    listBySession: (
      sessionId: string,
      params?: {
        provider?: string;
        model?: string;
        has_tools?: boolean;
        offset?: number;
        limit?: number;
      },
    ) => {
      const searchParams = new URLSearchParams();
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          if (v !== undefined) searchParams.set(k, String(v));
        });
      }
      return fetchJSON<LLMRequestSummary[]>(
        `/sessions/${sessionId}/requests?${searchParams}`,
      );
    },

    get: (id: string) => fetchJSON<LLMRequest>(`/requests/${id}`),

    getRaw: (id: string) => fetchJSON<RawCapture>(`/requests/${id}/raw`),
  },

  providers: {
    list: () => fetchJSON<ProviderMeta[]>("/providers"),
  },
};
