import { useState } from "react";
import { Badge } from "../common/Badge";
import { JsonViewer } from "../common/JsonViewer";

interface ToolCallBlockProps {
  toolName: string;
  toolInput: Record<string, unknown>;
  toolCallId: string;
}

/** Format a value for display as a key-value string. */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

/** Check if a value is simple enough to render inline (not a nested object/array). */
function isSimple(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return true;
  return false;
}

/** Check if all entries in the tool input are simple key-value pairs. */
function allSimple(input: Record<string, unknown>): boolean {
  return Object.values(input).every(isSimple);
}

export function ToolCallBlock({
  toolName,
  toolInput,
  toolCallId,
}: ToolCallBlockProps) {
  const [showRaw, setShowRaw] = useState(false);
  const entries = Object.entries(toolInput);
  const canShowKV = entries.length > 0 && allSimple(toolInput);

  return (
    <div className="rounded-lg bg-gray-800/60 border border-gray-700 border-l-4 border-l-blue-500 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-700/50">
        <Badge variant="blue" size="sm">
          {toolName}
        </Badge>
        <span className="text-[10px] text-gray-500 font-mono truncate flex-1">
          {toolCallId}
        </span>
        {canShowKV && (
          <button
            onClick={() => setShowRaw((v) => !v)}
            className="text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
          >
            {showRaw ? "KV" : "JSON"}
          </button>
        )}
      </div>

      {/* Body */}
      <div className="px-3 py-2 max-h-72 overflow-y-auto">
        {entries.length === 0 ? (
          <span className="text-xs text-gray-500 italic">No parameters</span>
        ) : canShowKV && !showRaw ? (
          <div className="space-y-1">
            {entries.map(([key, value]) => {
              const strVal = formatValue(value);
              const isLong = strVal.length > 120;
              return (
                <div key={key} className="flex gap-2 text-xs">
                  <span className="text-blue-400 shrink-0 font-mono">{key}</span>
                  {isLong ? (
                    <pre className="text-gray-300 font-mono whitespace-pre-wrap break-all min-w-0 flex-1">
                      {strVal}
                    </pre>
                  ) : (
                    <span className="text-gray-300 font-mono truncate min-w-0">
                      {strVal}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <JsonViewer data={toolInput} defaultExpandDepth={2} />
        )}
      </div>
    </div>
  );
}
