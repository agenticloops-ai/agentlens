import { useState, useMemo } from "react";
import clsx from "clsx";
import { JsonViewer } from "../common/JsonViewer";

interface ToolResultBlockProps {
  content: string;
  toolCallId: string;
  isError: boolean;
}

/** Try to parse content as JSON; returns parsed value or null. */
function tryParseJson(text: string): unknown | null {
  try {
    const trimmed = text.trim();
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      return JSON.parse(trimmed);
    }
  } catch {
    // not JSON
  }
  return null;
}

const COLLAPSE_THRESHOLD = 400;

export function ToolResultBlock({
  content,
  toolCallId,
  isError,
}: ToolResultBlockProps) {
  const isLong = content.length > COLLAPSE_THRESHOLD;
  const [expanded, setExpanded] = useState(!isLong);
  const parsedJson = useMemo(() => tryParseJson(content), [content]);

  return (
    <div
      className={clsx(
        "rounded-lg border border-l-4 overflow-hidden",
        isError
          ? "bg-red-950/30 border-gray-700 border-l-red-500"
          : "bg-gray-800/40 border-gray-700 border-l-green-500",
      )}
    >
      {/* Header */}
      <div
        className={clsx(
          "flex items-center gap-2 px-3 py-2",
          isLong && "cursor-pointer hover:bg-gray-700/30 transition-colors",
        )}
        onClick={isLong ? () => setExpanded((v) => !v) : undefined}
      >
        {isLong && (
          <svg
            className={`w-3 h-3 text-gray-500 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 5l7 7-7 7"
            />
          </svg>
        )}
        <span
          className={clsx(
            "text-xs font-medium",
            isError ? "text-red-400" : "text-green-400",
          )}
        >
          {isError ? "Error" : "Result"}
        </span>
        <span className="text-[10px] text-gray-500 font-mono truncate">
          {toolCallId}
        </span>
      </div>

      {/* Body */}
      {expanded && (
        <div
          className={clsx(
            "px-3 pb-3 max-h-80 overflow-y-auto border-t",
            isError ? "border-red-900/30" : "border-gray-700/50",
          )}
        >
          {parsedJson !== null ? (
            <div className="mt-2">
              <JsonViewer data={parsedJson} defaultExpandDepth={2} />
            </div>
          ) : (
            <pre
              className={clsx(
                "mt-2 text-xs font-mono whitespace-pre-wrap break-words leading-relaxed",
                isError ? "text-red-300" : "text-gray-300",
              )}
            >
              {content}
            </pre>
          )}
        </div>
      )}

      {!expanded && (
        <div className="px-3 pb-2">
          <p className="text-xs text-gray-500 truncate">
            {content.slice(0, 120)}
            {content.length > 120 ? "..." : ""}
          </p>
        </div>
      )}
    </div>
  );
}
