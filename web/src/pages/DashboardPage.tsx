import { useSessions } from "../api/hooks";
import { SessionList } from "../components/session/SessionList";

export function DashboardPage() {
  const { data: sessions, isLoading } = useSessions();

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-100 mb-6">Dashboard</h1>

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center gap-3 py-16 justify-center">
          <div className="h-5 w-5 rounded-full border-2 border-gray-600 border-t-blue-500 animate-spin" />
          <span className="text-sm text-gray-400">Loading sessions...</span>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && (!sessions || sessions.length === 0) && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="h-16 w-16 rounded-full bg-gray-800 border border-gray-700 flex items-center justify-center mb-4">
            <span className="text-2xl text-gray-500">&#9776;</span>
          </div>
          <h2 className="text-lg font-semibold text-gray-300 mb-2">
            No profiling sessions yet
          </h2>
          <p className="text-sm text-gray-500 max-w-md">
            Start the AgentLens proxy to capture LLM API calls. Sessions
            will appear here automatically as traffic flows through the proxy.
          </p>
          <div className="mt-6 bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm font-mono text-gray-400">
            agentlens start
          </div>
        </div>
      )}

      {/* Session list */}
      {sessions && sessions.length > 0 && (
        <SessionList sessions={sessions} />
      )}
    </div>
  );
}
