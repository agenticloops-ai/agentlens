import { useState } from "react";

interface ThinkingBlockProps {
  thinking: string;
}

export function ThinkingBlock({ thinking }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg bg-purple-900/20 border border-purple-800/30 overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-purple-900/30 transition-colors"
      >
        <svg
          className={`w-3.5 h-3.5 text-purple-400 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
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
        <span className="text-xs font-medium text-purple-300">
          Thinking
        </span>
        {!expanded && (
          <span className="text-xs text-purple-400/60 truncate ml-1 flex-1">
            {thinking.slice(0, 80)}
            {thinking.length > 80 ? "..." : ""}
          </span>
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3 border-t border-purple-800/30">
          <pre className="mt-2 text-xs font-mono text-purple-200/80 italic whitespace-pre-wrap break-words leading-relaxed max-h-80 overflow-y-auto">
            {thinking}
          </pre>
        </div>
      )}
    </div>
  );
}
