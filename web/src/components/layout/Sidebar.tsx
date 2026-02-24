import { NavLink, useNavigate, useParams } from "react-router-dom";
import { useSessions, useDeleteSession, useDeleteAllSessions } from "../../api/hooks";
import type { SessionSummary } from "../../types";

/** Ensure an ISO timestamp is treated as UTC (server stores naive UTC without Z). */
function utc(iso: string): number {
  return new Date(iso.endsWith("Z") ? iso : iso + "Z").getTime();
}

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - utc(iso)) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function SessionItem({
  session,
  onDelete,
}: {
  session: SessionSummary;
  onDelete: (id: string) => void;
}) {
  return (
    <NavLink
      to={`/session/${session.id}`}
      className={({ isActive }) =>
        [
          "group flex items-center gap-1 px-4 py-3 border-l-2 transition-colors",
          isActive
            ? "border-blue-500 bg-gray-800/60 text-gray-100"
            : "border-transparent hover:bg-gray-800/40 text-gray-400 hover:text-gray-200",
        ].join(" ")
      }
    >
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{session.name}</div>
        <div className="mt-1 flex items-center gap-3 text-xs text-gray-500">
          <span>{session.request_count} requests</span>
          <span>{timeAgo(session.started_at)}</span>
        </div>
      </div>
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onDelete(session.id);
        }}
        className="shrink-0 p-1 rounded text-gray-600 opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-900/30 transition-all"
        title="Delete session"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </NavLink>
  );
}

export function Sidebar() {
  const { data: sessions, isLoading } = useSessions();
  const deleteSession = useDeleteSession();
  const deleteAll = useDeleteAllSessions();
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId?: string }>();

  const handleDelete = (id: string) => {
    if (!confirm("Delete this session and all its data?")) return;
    deleteSession.mutate(id, {
      onSuccess: () => {
        if (sessionId === id) navigate("/");
      },
    });
  };

  const handleClearAll = () => {
    if (!confirm("Delete ALL sessions? This cannot be undone.")) return;
    deleteAll.mutate(undefined, {
      onSuccess: () => navigate("/"),
    });
  };

  return (
    <aside className="w-70 shrink-0 flex flex-col bg-gray-900 border-r border-gray-700 h-screen overflow-hidden">
      {/* Logo / Title */}
      <NavLink
        to="/"
        className="flex items-center gap-2 px-5 py-5 border-b border-gray-700"
      >
        <div className="h-7 w-7 rounded-md bg-blue-500 flex items-center justify-center text-xs font-bold text-white">
          AL
        </div>
        <span className="text-base font-semibold text-gray-100 tracking-tight">
          AgentLens
        </span>
      </NavLink>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-2">
        <div className="flex items-center justify-between px-4 py-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
            Sessions
          </span>
          {sessions && sessions.length > 0 && (
            <button
              onClick={handleClearAll}
              className="text-[10px] text-gray-600 hover:text-red-400 transition-colors"
              title="Delete all sessions"
            >
              Clear all
            </button>
          )}
        </div>

        {isLoading && (
          <div className="px-4 py-6 text-sm text-gray-500">Loading...</div>
        )}

        {!isLoading && (!sessions || sessions.length === 0) && (
          <div className="px-4 py-6 text-sm text-gray-500">
            No sessions yet
          </div>
        )}

        {sessions?.map((s) => (
          <SessionItem key={s.id} session={s} onDelete={handleDelete} />
        ))}
      </div>
    </aside>
  );
}
