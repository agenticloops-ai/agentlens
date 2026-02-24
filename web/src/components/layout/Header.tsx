import { useParams, Link } from "react-router-dom";
import { useSession, useRequest } from "../../api/hooks";
import { useLiveStore } from "../../stores/liveStore";

function Separator() {
  return <span className="text-gray-600 mx-1.5">/</span>;
}

export function Header() {
  const { sessionId, requestId } = useParams<{
    sessionId?: string;
    requestId?: string;
  }>();

  const { data: session } = useSession(sessionId ?? "");
  const { data: request } = useRequest(requestId ?? "");
  const connected = useLiveStore((s) => s.connected);

  return (
    <header className="h-12 shrink-0 flex items-center justify-between px-5 border-b border-gray-700 bg-gray-900/50">
      {/* Breadcrumb */}
      <nav className="flex items-center text-sm">
        <Link
          to="/"
          className="text-gray-400 hover:text-gray-200 transition-colors"
        >
          Dashboard
        </Link>

        {sessionId && (
          <>
            <Separator />
            <Link
              to={`/session/${sessionId}`}
              className="text-gray-400 hover:text-gray-200 transition-colors truncate max-w-60"
            >
              {session?.name ?? "Session"}
            </Link>
          </>
        )}

        {requestId && (
          <>
            <Separator />
            <span className="text-gray-200 truncate max-w-48">
              {request
                ? `${request.model} - ${request.status}`
                : "Request"}
            </span>
          </>
        )}
      </nav>

      {/* Live indicator */}
      <div className="flex items-center gap-2 text-xs">
        {connected ? (
          <>
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
            </span>
            <span className="text-green-400">Live</span>
          </>
        ) : (
          <>
            <span className="relative flex h-2 w-2">
              <span className="relative inline-flex rounded-full h-2 w-2 bg-gray-500" />
            </span>
            <span className="text-gray-500">Disconnected</span>
          </>
        )}
      </div>
    </header>
  );
}
