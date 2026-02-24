import type { LLMRequestSummary } from "../../types";
import { RequestSummaryRow } from "./RequestSummaryRow";

interface RequestTimelineProps {
  requests: LLMRequestSummary[];
  sessionId: string;
  sessionStartedAt: string;
}

export function RequestTimeline({
  requests,
  sessionId,
  sessionStartedAt,
}: RequestTimelineProps) {
  // Sort by timestamp ascending
  const sorted = [...requests].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );

  // Find the maximum duration for proportional bar rendering
  const maxDurationMs = sorted.reduce(
    (max, r) => Math.max(max, r.duration_ms ?? 0),
    0,
  );

  if (sorted.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-500 text-sm">
        No requests recorded yet
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-3 py-2 text-[10px] uppercase tracking-wider text-gray-500 border-b border-gray-700">
        <span className="w-14 text-right">Time</span>
        <span className="w-2" />
        <span className="w-20">Model</span>
        <span className="w-24">Duration</span>
        <span className="w-28">Tokens</span>
        <span className="w-16">Flags</span>
        <span className="flex-1">Preview</span>
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-y-auto">
        {sorted.map((req) => (
          <RequestSummaryRow
            key={req.id}
            request={req}
            sessionId={sessionId}
            sessionStartedAt={sessionStartedAt}
            maxDurationMs={maxDurationMs}
          />
        ))}
      </div>
    </div>
  );
}
