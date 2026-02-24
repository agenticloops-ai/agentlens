import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import clsx from "clsx";
import { useRequest, useRawCapture } from "../api/hooks";
import { RequestDetail } from "../components/request/RequestDetail";
import { SystemPromptBlock } from "../components/conversation/SystemPromptBlock";
import { ToolDefinitionPanel } from "../components/tools/ToolDefinitionPanel";
import { ConversationThread } from "../components/conversation/ConversationThread";
import { JsonViewer } from "../components/common/JsonViewer";

type Tab = "conversation" | "raw";

export function RequestDetailPage() {
  const { sessionId, requestId } = useParams<{
    sessionId: string;
    requestId: string;
  }>();
  const [activeTab, setActiveTab] = useState<Tab>("conversation");

  const { data: request, isLoading, error } = useRequest(requestId ?? "");

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sm text-gray-400">Loading request...</div>
      </div>
    );
  }

  if (error || !request) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-sm text-red-400">
          {error ? String(error) : "Request not found"}
        </p>
        {sessionId && (
          <Link
            to={`/session/${sessionId}`}
            className="text-sm text-blue-400 hover:text-blue-300 underline"
          >
            Back to session
          </Link>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Back link */}
      {sessionId && (
        <Link
          to={`/session/${sessionId}`}
          className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15 19l-7-7 7-7"
            />
          </svg>
          Back to session
        </Link>
      )}

      {/* Header bar */}
      <RequestDetail request={request} />

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-700">
        <TabButton
          active={activeTab === "conversation"}
          onClick={() => setActiveTab("conversation")}
        >
          Conversation
        </TabButton>
        <TabButton
          active={activeTab === "raw"}
          onClick={() => setActiveTab("raw")}
        >
          Raw JSON
        </TabButton>
      </div>

      {/* Tab content */}
      {activeTab === "conversation" ? (
        <ConversationTab request={request} />
      ) : (
        <RawJsonTab requestId={requestId ?? ""} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab button
// ---------------------------------------------------------------------------

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px",
        active
          ? "border-blue-500 text-blue-400"
          : "border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-600",
      )}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Conversation tab
// ---------------------------------------------------------------------------

function ConversationTab({
  request,
}: {
  request: NonNullable<ReturnType<typeof useRequest>["data"]>;
}) {
  return (
    <div className="space-y-4">
      {/* System prompt */}
      {request.system_prompt && (
        <SystemPromptBlock prompt={request.system_prompt} />
      )}

      {/* Tool definitions */}
      {request.tools.length > 0 && (
        <ToolDefinitionPanel tools={request.tools} />
      )}

      {/* Conversation thread */}
      <ConversationThread
        messages={request.messages}
        responseMessages={request.response_messages}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Raw JSON tab
// ---------------------------------------------------------------------------

function RawJsonTab({ requestId }: { requestId: string }) {
  const { data: raw, isLoading, error } = useRawCapture(requestId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <span className="text-sm text-gray-400">Loading raw data...</span>
      </div>
    );
  }

  if (error || !raw) {
    return (
      <div className="text-sm text-gray-500">
        {error ? String(error) : "No raw capture data available."}
      </div>
    );
  }

  // For streaming responses, response_body is empty — show SSE events instead
  const hasSSE = raw.is_streaming && raw.sse_events && raw.sse_events.length > 0;
  const responseData = hasSSE ? raw.sse_events : raw.response_body;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Request panel */}
      <div className="rounded-lg bg-gray-800 border border-gray-700 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-gray-700 flex items-center justify-between">
          <span className="text-sm font-medium text-gray-300">Request</span>
          <span className="text-xs text-gray-500 font-mono">
            {raw.request_method} {raw.request_url}
          </span>
        </div>
        <div className="p-4 max-h-[70vh] overflow-y-auto">
          <JsonViewer data={raw.request_body} defaultExpandDepth={2} />
        </div>
      </div>

      {/* Response panel */}
      <div className="rounded-lg bg-gray-800 border border-gray-700 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-gray-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-300">Response</span>
            {hasSSE && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-900/50 text-purple-400">
                SSE · {raw.sse_events.length} events
              </span>
            )}
          </div>
          <span className="text-xs text-gray-500 font-mono">
            Status {raw.response_status}
          </span>
        </div>
        <div className="p-4 max-h-[70vh] overflow-y-auto">
          <JsonViewer data={responseData} defaultExpandDepth={hasSSE ? 1 : 2} />
        </div>
      </div>
    </div>
  );
}
