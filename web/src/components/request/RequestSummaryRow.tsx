import { Link } from "react-router-dom";
import type { LLMRequestSummary } from "../../types";
import { useProviderMeta } from "../../hooks/useProviderMeta";

/** Provider color dot */
function ProviderDot({ color }: { color: string }) {
  return (
    <span
      className="inline-block h-2 w-2 rounded-full shrink-0"
      style={{ backgroundColor: color }}
    />
  );
}

/** Model badge with provider-colored background */
function ModelBadge({ color, model }: { color: string; model: string }) {
  return (
    <span
      className="inline-block px-1.5 py-0.5 rounded text-[11px] font-medium"
      style={{ backgroundColor: `${color}20`, color }}
    >
      {model}
    </span>
  );
}

/** Small icon-style badge */
function FeatureBadge({
  title,
  children,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center justify-center h-5 w-5 rounded text-[11px] ${className}`}
    >
      {children}
    </span>
  );
}

function captureModeLabel(mode: string): string {
  return mode === "transparent" ? "Transparent" : "Explicit";
}

interface RequestSummaryRowProps {
  request: LLMRequestSummary;
  sessionId: string;
  sessionStartedAt: string;
  maxDurationMs: number;
}

export function RequestSummaryRow({
  request,
  sessionId,
  sessionStartedAt,
  maxDurationMs,
}: RequestSummaryRowProps) {
  const getProvider = useProviderMeta();
  const providerColor = getProvider(request.provider).color;

  // Relative time from session start (both are UTC, diff is timezone-safe)
  const offsetMs =
    new Date(request.timestamp + "Z").getTime() - new Date(sessionStartedAt + "Z").getTime();
  const offsetSec = offsetMs / 1000;
  const relativeTime =
    offsetSec < 0
      ? `${offsetSec.toFixed(1)}s`
      : `+${offsetSec < 100 ? offsetSec.toFixed(1) : Math.round(offsetSec)}s`;

  // Duration bar width (percentage of max)
  const durationPct =
    request.duration_ms != null && maxDurationMs > 0
      ? Math.max(2, (request.duration_ms / maxDurationMs) * 100)
      : 0;

  const isError = request.status === "error";
  const hasTools = request.has_tools;
  const hasThinking = request.has_thinking;

  return (
    <Link
      to={`/session/${sessionId}/request/${request.id}`}
      className="flex items-center gap-3 px-3 py-2.5 border-b border-gray-800 hover:bg-gray-800/60 transition-colors group"
    >
      {/* Timestamp */}
      <span className="text-[11px] font-mono text-gray-500 w-14 text-right shrink-0">
        {relativeTime}
      </span>

      {/* Provider dot */}
      <ProviderDot color={providerColor} />

      {/* Model badge */}
      <ModelBadge color={providerColor} model={request.model} />

      <span className="text-[10px] uppercase tracking-wider text-gray-500 w-16 shrink-0">
        {request.capture_label ?? captureModeLabel(request.capture_mode)}
      </span>

      {/* Duration bar */}
      <div className="w-24 shrink-0">
        {request.duration_ms != null ? (
          <div className="flex items-center gap-1.5">
            <div className="flex-1 h-1.5 rounded-full bg-gray-700 overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${durationPct}%`, backgroundColor: `${providerColor}99` }}
              />
            </div>
            <span className="text-[10px] font-mono text-gray-500 w-12 text-right">
              {request.duration_ms < 1000
                ? `${Math.round(request.duration_ms)}ms`
                : `${(request.duration_ms / 1000).toFixed(1)}s`}
            </span>
          </div>
        ) : (
          <span className="text-[10px] text-gray-600">--</span>
        )}
      </div>

      {/* Token counts */}
      <div className="flex items-center gap-2 text-[11px] shrink-0 w-28">
        <span className="text-blue-400">
          <span className="text-gray-600">in:</span> {request.usage.input_tokens.toLocaleString()}
        </span>
        <span className="text-purple-400">
          <span className="text-gray-600">out:</span> {request.usage.output_tokens.toLocaleString()}
        </span>
      </div>

      {/* Feature badges */}
      <div className="flex items-center gap-0.5 shrink-0 w-16">
        {hasTools && (
          <FeatureBadge title="Tools" className="text-gray-400">
            &#128295;
          </FeatureBadge>
        )}
        {isError && (
          <FeatureBadge title="Error" className="text-red-400 bg-red-900/30">
            &#10007;
          </FeatureBadge>
        )}
        {hasThinking && (
          <FeatureBadge title="Thinking" className="text-purple-400/70">
            &#129504;
          </FeatureBadge>
        )}
      </div>

      {/* Preview text */}
      <span className="text-xs text-gray-500 truncate min-w-0 flex-1">
        {request.preview_text || ""}
      </span>
    </Link>
  );
}
