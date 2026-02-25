import { useState, useRef, useEffect } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { useSessions, useDeleteSession, useDeleteAllSessions, useCreateSession, useRenameSession } from "../../api/hooks";
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
  onRename,
}: {
  session: SessionSummary;
  onDelete: (id: string) => void;
  onRename: (id: string, name: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(session.name);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== session.name) {
      onRename(session.id, trimmed);
    } else {
      setDraft(session.name);
    }
    setEditing(false);
  };

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
        {editing ? (
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") {
                setDraft(session.name);
                setEditing(false);
              }
            }}
            onClick={(e) => e.preventDefault()}
            className="w-full text-sm font-medium bg-gray-700 text-gray-100 px-1.5 py-0.5 rounded border border-gray-600 outline-none focus:border-blue-500"
          />
        ) : (
          <div
            className="text-sm font-medium truncate"
            onDoubleClick={(e) => {
              e.preventDefault();
              setDraft(session.name);
              setEditing(true);
            }}
          >
            {session.name}
          </div>
        )}
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
  const createSession = useCreateSession();
  const renameSession = useRenameSession();
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

  const handleNewSession = () => {
    createSession.mutate(undefined, {
      onSuccess: (data) => navigate(`/session/${data.id}`),
    });
  };

  const handleRename = (id: string, name: string) => {
    renameSession.mutate({ id, name });
  };

  return (
    <aside className="w-70 shrink-0 flex flex-col bg-gray-900 border-r border-gray-700 h-screen overflow-hidden">
      {/* Logo / Title */}
      <NavLink
        to="/"
        className="h-12 shrink-0 flex items-center gap-2 px-5 border-b border-gray-700"
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
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
              Sessions
            </span>
            <button
              onClick={handleNewSession}
              disabled={createSession.isPending}
              className="flex items-center justify-center h-4.5 w-4.5 rounded bg-gray-700 text-gray-400 hover:bg-blue-600 hover:text-white transition-colors disabled:opacity-50"
              title="New session"
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </button>
          </div>
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
          <SessionItem key={s.id} session={s} onDelete={handleDelete} onRename={handleRename} />
        ))}
      </div>
    </aside>
  );
}
