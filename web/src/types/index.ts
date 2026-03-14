// Re-export all generated types from Pydantic models
export type {
  ContentBlock,
  ContentBlockType,
  ImageContent,
  LLMRequest,
  Message,
  MessageRole,
  Provider,
  RawCapture,
  RequestStatus,
  Session,
  SessionStats,
  StopReason,
  TextContent,
  ThinkingContent,
  TokenUsage,
  ToolDefinition,
  ToolResultContent,
  ToolUseContent,
} from "./generated";

// ---------------------------------------------------------------------------
// API response types (not generated from Pydantic)
// ---------------------------------------------------------------------------

/**
 * Lightweight session summary returned by the list-sessions endpoint.
 * A subset of `Session` suitable for list/table views.
 */
export interface SessionSummary {
  id: string;
  name: string;
  started_at: string;
  ended_at: string | null;
  request_count: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

/**
 * Lightweight LLM request summary used in list views and live events.
 * Contains pre-computed convenience fields that avoid transferring the
 * full message payloads.
 */
export interface LLMRequestSummary {
  id: string;
  session_id: string;
  timestamp: string;
  duration_ms: number | null;
  provider: string;
  model: string;
  capture_mode: string;
  capture_label: string | null;
  status: string;
  usage: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number | null;
  };

  /** Short preview of the assistant response text. */
  preview_text: string;
  /** Whether the request included tool definitions. */
  has_tools: boolean;
  /** Whether the response contains thinking/reasoning blocks. */
  has_thinking: boolean;
}

// ---------------------------------------------------------------------------
// WebSocket event types
// ---------------------------------------------------------------------------

export interface NewRequestEvent {
  type: "new_request";
  data: LLMRequestSummary;
}

export interface SessionUpdatedEvent {
  type: "session_updated";
  data: SessionSummary;
}

/** Union of all WebSocket events the client may receive. */
export type LiveEvent = NewRequestEvent | SessionUpdatedEvent;
