import { useState, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useSession, useSessionRequests, useRenameSession } from "../api/hooks";
import { RequestTimeline } from "../components/request/RequestTimeline";
import { TokenUsageChart } from "../components/stats/TokenUsageChart";
import { LatencyChart } from "../components/stats/LatencyChart";
import { CostSummary } from "../components/stats/CostSummary";
import { ExportMenu } from "../components/common/ExportMenu";
import { useProviderMeta } from "../hooks/useProviderMeta";

/** Ensure an ISO timestamp is treated as UTC (server stores naive UTC without Z). */
function utc(iso: string): number {
  return new Date(iso.endsWith("Z") ? iso : iso + "Z").getTime();
}

function formatDuration(startedAt: string, endedAt: string | null): string {
  const end = endedAt ? utc(endedAt) : Date.now();
  const ms = end - utc(startedAt);
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

function StatBox({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">
        {label}
      </div>
      <div className="text-sm font-semibold text-gray-200 leading-tight">{value}</div>
      {sub && <div className="text-[11px] text-gray-500">{sub}</div>}
    </div>
  );
}

export function SessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { data: session, isLoading: sessionLoading } = useSession(sessionId ?? "");
  const { data: requests, isLoading: requestsLoading } = useSessionRequests(
    sessionId ?? "",
  );
  const renameSession = useRenameSession();
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editingName) nameInputRef.current?.select();
  }, [editingName]);

  const commitRename = () => {
    const trimmed = nameDraft.trim();
    if (trimmed && trimmed !== session?.name && sessionId) {
      renameSession.mutate({ id: sessionId, name: trimmed });
    }
    setEditingName(false);
  };

  // Debounce search query to avoid spamming API
  const [debouncedQuery, setDebouncedQuery] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchQuery), 250);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const { data: filteredRequests } = useSessionRequests(
    sessionId ?? "",
    debouncedQuery ? { q: debouncedQuery } : undefined,
  );

  // When searching, show filtered results; otherwise show all
  const safeRequests = debouncedQuery ? (filteredRequests ?? []) : (requests ?? []);

  // Keyboard shortcut: / to focus search
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;
      if (e.key === "/") {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const getProvider = useProviderMeta();

  // -------------------------------------------------------------------------
  // Early returns (after all hooks)
  // -------------------------------------------------------------------------

  if (sessionLoading || requestsLoading) {
    return (
      <div className="flex items-center gap-3 py-16 justify-center">
        <div className="h-5 w-5 rounded-full border-2 border-gray-600 border-t-blue-500 animate-spin" />
        <span className="text-sm text-gray-400">Loading session...</span>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="text-gray-400 text-sm py-16 text-center">
        Session not found
      </div>
    );
  }

  const isActive = !session.ended_at;
  const stats = session.stats;

  return (
    <div className="flex flex-col lg:flex-row gap-4 h-full">
      {/* Left panel: Request timeline */}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex-1 bg-gray-800/40 border border-gray-700 rounded-lg flex flex-col min-h-0">
          {/* Session header (inside the timeline card so tops align) */}
          <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-700">
            <div className="min-w-0">
              {editingName ? (
                <input
                  ref={nameInputRef}
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  onBlur={commitRename}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename();
                    if (e.key === "Escape") setEditingName(false);
                  }}
                  className="text-base font-bold bg-gray-700 text-gray-100 px-1.5 py-0.5 rounded border border-gray-600 outline-none focus:border-blue-500 w-full max-w-xs"
                />
              ) : (
                <h1
                  className="text-base font-bold text-gray-100 truncate cursor-pointer hover:text-blue-400 transition-colors"
                  onClick={() => {
                    setNameDraft(session.name || "");
                    setEditingName(true);
                  }}
                  title="Click to rename"
                >
                  {session.name || "Unnamed Session"}
                </h1>
              )}
              <div className="flex items-center gap-3 text-xs text-gray-500">
                {isActive && (
                  <span className="flex items-center gap-1.5 text-green-400">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
                    </span>
                    Active
                  </span>
                )}
                <span>{formatDuration(session.started_at, session.ended_at)}</span>
                <span>{stats.total_requests} requests</span>
              </div>
            </div>
            <ExportMenu
              sessionId={sessionId ?? ""}
              sessionName={session.name || "session"}
            />
          </div>

          {/* Search bar */}
          <div className="px-3 py-2 border-b border-gray-700">
            <div className="relative">
              <svg
                className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
                />
              </svg>
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setSearchQuery("");
                    searchInputRef.current?.blur();
                  }
                }}
                placeholder="Search by tool, model, content... (press /)"
                className="w-full pl-8 pr-8 py-1.5 text-sm bg-gray-800 border border-gray-700 rounded text-gray-200 placeholder-gray-500 outline-none focus:border-gray-500 transition-colors"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
            {debouncedQuery && (
              <div className="text-[11px] text-gray-500 mt-1">
                {safeRequests.length} result{safeRequests.length !== 1 ? "s" : ""}
                {requests ? ` of ${requests.length}` : ""}
              </div>
            )}
          </div>

          {/* Timeline rows */}
          <RequestTimeline
            requests={safeRequests}
            sessionId={sessionId ?? ""}
            sessionStartedAt={session.started_at}
          />
        </div>
      </div>

      {/* Right panel: Stats (compact) */}
      <div className="w-full lg:w-72 shrink-0 space-y-3">
        {/* Quick stats */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
          <h2 className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-2">
            Session Stats
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <StatBox
              label="Total Requests"
              value={String(stats.total_requests)}
            />
            <StatBox
              label="Total Tokens"
              value={stats.total_tokens.toLocaleString()}
              sub={`In: ${stats.total_input_tokens.toLocaleString()} / Out: ${stats.total_output_tokens.toLocaleString()}`}
            />
            <StatBox
              label="Avg Duration"
              value={
                stats.avg_duration_ms != null
                  ? stats.avg_duration_ms >= 1000
                    ? `${(stats.avg_duration_ms / 1000).toFixed(1)}s`
                    : `${Math.round(stats.avg_duration_ms)}ms`
                  : "--"
              }
            />
            <StatBox
              label="Avg Tokens/Req"
              value={
                stats.avg_tokens_per_request != null
                  ? Math.round(stats.avg_tokens_per_request).toLocaleString()
                  : "--"
              }
            />
          </div>

          {/* Provider / model badges */}
          {(stats.providers_used.length > 0 || stats.models_used.length > 0) && (
            <div className="mt-2 pt-2 border-t border-gray-700">
              <div className="flex flex-wrap gap-1">
                {stats.providers_used.map((p) => {
                  const meta = getProvider(p);
                  return (
                    <span
                      key={p}
                      className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium"
                      style={{ backgroundColor: `${meta.color}20`, color: meta.color }}
                    >
                      {p}
                    </span>
                  );
                })}
                {stats.models_used.map((m) => (
                  <span
                    key={m}
                    className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-700 text-gray-300"
                  >
                    {m}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Cost summary (compact — total + avg on one line) */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
          <h2 className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-2">
            Cost
          </h2>
          <CostSummary stats={stats} requests={safeRequests} />
        </div>

        {/* Token usage chart */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
          <h2 className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-2">
            Token Usage
          </h2>
          <TokenUsageChart requests={safeRequests} />
        </div>

        {/* Latency chart */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
          <h2 className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-2">
            Latency
          </h2>
          <LatencyChart requests={safeRequests} />
        </div>
      </div>
    </div>
  );
}
