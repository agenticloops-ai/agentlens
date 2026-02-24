import { useState } from "react";

interface SystemPromptBlockProps {
  prompt: string | string[];
}

/** Render a single system prompt part. */
function PromptPart({ text, index, total }: { text: string; index: number; total: number }) {
  return (
    <div className={total > 1 ? "relative pl-4 border-l-2 border-gray-600" : ""}>
      {total > 1 && (
        <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1.5">
          Part {index + 1} of {total}
        </div>
      )}
      <pre className="text-xs font-mono text-gray-300 whitespace-pre-wrap break-words leading-relaxed">
        {text}
      </pre>
    </div>
  );
}

export function SystemPromptBlock({ prompt }: SystemPromptBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const parts = Array.isArray(prompt) ? prompt : [prompt];
  const previewText = parts[0] || "";

  return (
    <div className="rounded-lg bg-gray-800 border border-gray-700 overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-gray-750 transition-colors"
      >
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
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
        <span className="text-sm font-medium text-gray-300">
          System Prompt
        </span>
        {parts.length > 1 && (
          <span className="text-[11px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-400">
            {parts.length} parts
          </span>
        )}
        {!expanded && (
          <span className="text-xs text-gray-500 truncate ml-2 flex-1">
            {previewText.slice(0, 100)}
            {previewText.length > 100 ? "..." : ""}
          </span>
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-700">
          <div className="mt-3 space-y-4 max-h-96 overflow-y-auto">
            {parts.map((part, i) => (
              <PromptPart key={i} text={part} index={i} total={parts.length} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
