import clsx from "clsx";
import type { Message, ContentBlock, MessageRole } from "../../types";
import { ThinkingBlock } from "../thinking/ThinkingBlock";
import { ToolCallBlock } from "../tools/ToolCallBlock";
import { ToolResultBlock } from "../tools/ToolResultBlock";
import { Badge } from "../common/Badge";

interface MessageBubbleProps {
  message: Message;
}

interface RoleStyle {
  label: string;
  barColor: string;
  badgeVariant: "default" | "green" | "orange" | "blue" | "red" | "purple";
  bgColor: string;
}

const roleConfig: Record<MessageRole, RoleStyle> = {
  user: {
    label: "User",
    barColor: "bg-blue-500",
    badgeVariant: "blue",
    bgColor: "bg-gray-800",
  },
  assistant: {
    label: "Assistant",
    barColor: "bg-purple-500",
    badgeVariant: "purple",
    bgColor: "bg-gray-800/50",
  },
  tool: {
    label: "Tool",
    barColor: "bg-gray-500",
    badgeVariant: "default",
    bgColor: "bg-gray-800/30",
  },
  system: {
    label: "System",
    barColor: "bg-orange-500",
    badgeVariant: "orange",
    bgColor: "bg-gray-800/40",
  },
};

export function MessageBubble({ message }: MessageBubbleProps) {
  const config = roleConfig[message.role];

  return (
    <div className={clsx("flex gap-3 rounded-lg p-4", config.bgColor)}>
      {/* Left role indicator bar */}
      <div className={clsx("w-1 shrink-0 rounded-full", config.barColor)} />

      {/* Content */}
      <div className="flex-1 min-w-0 space-y-3">
        {/* Role label */}
        <div className="flex items-center gap-2">
          <Badge variant={config.badgeVariant} size="sm">
            {config.label}
          </Badge>
        </div>

        {/* Content blocks */}
        {message.content.map((block, idx) => (
          <ContentBlockRenderer key={idx} block={block} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Content block dispatcher
// ---------------------------------------------------------------------------

function ContentBlockRenderer({ block }: { block: ContentBlock }) {
  switch (block.type) {
    case "text":
      return <TextRenderer text={block.text} />;
    case "thinking":
      return <ThinkingBlock thinking={block.thinking} />;
    case "tool_use":
      return (
        <ToolCallBlock
          toolName={block.tool_name}
          toolInput={block.tool_input}
          toolCallId={block.tool_call_id}
        />
      );
    case "tool_result":
      return (
        <ToolResultBlock
          content={block.content}
          toolCallId={block.tool_call_id}
          isError={block.is_error}
        />
      );
    case "image":
      return (
        <Badge variant="default" size="md">
          [Image: {block.media_type}]
        </Badge>
      );
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Simple text renderer with whitespace preservation
// ---------------------------------------------------------------------------

function TextRenderer({ text }: { text: string }) {
  // Basic rendering: preserve whitespace and newlines, detect code fences
  const segments = text.split(/(```[\s\S]*?```)/g);

  return (
    <div className="text-xs font-mono text-gray-300 leading-relaxed">
      {segments.map((segment, idx) => {
        if (segment.startsWith("```") && segment.endsWith("```")) {
          // Inline code block
          const inner = segment.slice(3, -3);
          const newlineIdx = inner.indexOf("\n");
          const lang = newlineIdx > 0 ? inner.slice(0, newlineIdx).trim() : "";
          const code =
            newlineIdx > 0 ? inner.slice(newlineIdx + 1) : inner;
          return (
            <pre
              key={idx}
              className="my-2 p-3 rounded bg-gray-900 border border-gray-700 text-xs font-mono text-gray-300 overflow-x-auto"
            >
              {lang && (
                <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
                  {lang}
                </div>
              )}
              <code>{code}</code>
            </pre>
          );
        }

        // Regular text: preserve whitespace, render inline code with backticks
        const parts = segment.split(/(`[^`]+`)/g);
        return (
          <span key={idx}>
            {parts.map((part, pidx) => {
              if (part.startsWith("`") && part.endsWith("`")) {
                return (
                  <code
                    key={pidx}
                    className="px-1 py-0.5 rounded bg-gray-700 text-gray-200 text-xs"
                  >
                    {part.slice(1, -1)}
                  </code>
                );
              }
              // Preserve whitespace/newlines
              return (
                <span key={pidx} className="whitespace-pre-wrap break-words">
                  {part}
                </span>
              );
            })}
          </span>
        );
      })}
    </div>
  );
}
