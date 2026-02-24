import type { LLMRequest } from "../../types";
import { Badge } from "../common/Badge";
import { useProviderMeta } from "../../hooks/useProviderMeta";

interface RequestDetailProps {
  request: LLMRequest;
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "--";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatTokens(n: number): string {
  return n.toLocaleString();
}

function formatCost(cost: number | null): string {
  if (cost === null) return "--";
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

const stopReasonVariant: Record<
  string,
  "default" | "green" | "orange" | "blue" | "red"
> = {
  end_turn: "green",
  max_tokens: "orange",
  stop_sequence: "default",
  tool_use: "blue",
  error: "red",
  unknown: "default",
};

export function RequestDetail({ request }: RequestDetailProps) {
  const getProvider = useProviderMeta();
  const providerColor = getProvider(request.provider).color;

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg bg-gray-800 border border-gray-700 px-4 py-3">
      {/* Provider */}
      <span
        className="inline-flex items-center rounded-full font-medium whitespace-nowrap px-2 py-0.5 text-xs"
        style={{ backgroundColor: `${providerColor}20`, color: providerColor }}
      >
        {request.provider}
      </span>

      {/* Model */}
      <span className="text-sm font-medium text-gray-200">
        {request.model}
      </span>

      {/* Separator */}
      <span className="text-gray-700">|</span>

      {/* Timestamp */}
      <span className="text-xs text-gray-400">
        {formatTimestamp(request.timestamp)}
      </span>

      {/* Duration */}
      <span className="text-xs text-gray-400">
        {formatDuration(request.duration_ms)}
      </span>

      {/* Streaming badge */}
      {request.is_streaming && (
        <Badge variant="orange" size="sm">
          <svg
            className="w-3 h-3 mr-0.5"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" />
          </svg>
          Stream
        </Badge>
      )}

      {/* Stop reason */}
      {request.stop_reason && (
        <Badge
          variant={stopReasonVariant[request.stop_reason] ?? "default"}
          size="sm"
        >
          {request.stop_reason}
        </Badge>
      )}

      {/* Separator */}
      <span className="text-gray-700">|</span>

      {/* Token counts */}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-gray-400">
          In:{" "}
          <span className="text-gray-300 font-medium">
            {formatTokens(request.usage.input_tokens)}
          </span>
        </span>
        <span className="text-gray-600">/</span>
        <span className="text-gray-400">
          Out:{" "}
          <span className="text-gray-300 font-medium">
            {formatTokens(request.usage.output_tokens)}
          </span>
        </span>
      </div>

      {/* Cost */}
      <span className="text-xs text-gray-400">
        {formatCost(request.usage.estimated_cost_usd)}
      </span>
    </div>
  );
}
