import type { Message } from "../../types";
import { MessageBubble } from "./MessageBubble";

interface ConversationThreadProps {
  messages: Message[];
  responseMessages: Message[];
}

export function ConversationThread({
  messages,
  responseMessages,
}: ConversationThreadProps) {
  return (
    <div className="space-y-3">
      {/* Input messages */}
      {messages.map((msg, idx) => (
        <MessageBubble key={`input-${idx}`} message={msg} />
      ))}

      {/* Visual separator between input and response */}
      {messages.length > 0 && responseMessages.length > 0 && (
        <div className="flex items-center gap-3 py-2">
          <div className="flex-1 h-px bg-gray-700" />
          <span className="text-xs text-gray-500 font-medium uppercase tracking-wider">
            Response
          </span>
          <div className="flex-1 h-px bg-gray-700" />
        </div>
      )}

      {/* Response messages */}
      {responseMessages.map((msg, idx) => (
        <MessageBubble key={`response-${idx}`} message={msg} />
      ))}
    </div>
  );
}
