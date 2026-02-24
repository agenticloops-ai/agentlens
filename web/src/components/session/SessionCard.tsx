import { Link } from "react-router-dom";
import type { SessionSummary } from "../../types";

function formatDuration(startedAt: string, endedAt: string | null): string {
  if (!endedAt) return "Active";
  const ms = new Date(endedAt).getTime() - new Date(startedAt).getTime();
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

function formatTokens(n: number): string {
  return n.toLocaleString();
}

function formatCost(cost: number): string {
  return `$${cost.toFixed(2)}`;
}

export function SessionCard({ session }: { session: SessionSummary }) {
  const isActive = !session.ended_at;

  return (
    <Link
      to={`/session/${session.id}`}
      className="block bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-gray-500 hover:bg-gray-750 transition-all duration-200 group"
    >
      {/* Session name */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-100 truncate group-hover:text-white">
          {session.name || "Unnamed Session"}
        </h3>
        {isActive && (
          <span className="flex items-center gap-1.5 text-xs text-green-400">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
            </span>
            Active
          </span>
        )}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-3 text-xs">
        {/* Duration */}
        <div>
          <div className="text-gray-500 mb-0.5">Duration</div>
          <div className={isActive ? "text-green-400 font-medium" : "text-gray-300"}>
            {formatDuration(session.started_at, session.ended_at)}
          </div>
        </div>

        {/* Requests */}
        <div>
          <div className="text-gray-500 mb-0.5">Requests</div>
          <div className="text-gray-300">{session.request_count}</div>
        </div>

        {/* Tokens */}
        <div>
          <div className="text-gray-500 mb-0.5">Tokens</div>
          <div className="text-gray-300">{formatTokens(session.total_tokens)}</div>
        </div>

        {/* Cost */}
        <div>
          <div className="text-gray-500 mb-0.5">Cost</div>
          <div className="text-gray-300">{formatCost(session.estimated_cost_usd)}</div>
        </div>
      </div>
    </Link>
  );
}
