// Auto-generated from Pydantic models — do not edit manually

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type Provider = "openai" | "anthropic" | "unknown";

export type MessageRole = "system" | "user" | "assistant" | "tool";

export type ContentBlockType =
  | "text"
  | "image"
  | "thinking"
  | "tool_use"
  | "tool_result";

export type StopReason =
  | "end_turn"
  | "max_tokens"
  | "stop_sequence"
  | "tool_use"
  | "error"
  | "unknown";

export type RequestStatus = "success" | "error" | "timeout" | "in_progress";

// ---------------------------------------------------------------------------
// Content blocks (discriminated union on `type`)
// ---------------------------------------------------------------------------

export interface TextContent {
  type: "text";
  text: string;
}

export interface ImageContent {
  type: "image";
  media_type: string;
  source_type: string;
  has_data: boolean;
}

export interface ThinkingContent {
  type: "thinking";
  thinking: string;
}

export interface ToolUseContent {
  type: "tool_use";
  tool_call_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
}

export interface ToolResultContent {
  type: "tool_result";
  tool_call_id: string;
  content: string;
  is_error: boolean;
}

export type ContentBlock =
  | TextContent
  | ImageContent
  | ThinkingContent
  | ToolUseContent
  | ToolResultContent;

// ---------------------------------------------------------------------------
// Message
// ---------------------------------------------------------------------------

export interface Message {
  role: MessageRole;
  content: ContentBlock[];
}

// ---------------------------------------------------------------------------
// Tool definition
// ---------------------------------------------------------------------------

export interface ToolDefinition {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  is_mcp: boolean;
  mcp_server_name: string | null;
}

// ---------------------------------------------------------------------------
// Token usage
// ---------------------------------------------------------------------------

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
}

// ---------------------------------------------------------------------------
// LLM Request (central unit)
// ---------------------------------------------------------------------------

export interface LLMRequest {
  id: string;
  session_id: string;
  raw_capture_id: string;
  capture_mode: string;
  capture_label: string | null;
  capture_metadata: Record<string, unknown>;

  // Timing
  timestamp: string; // ISO-8601 datetime
  duration_ms: number | null;
  time_to_first_token_ms: number | null;

  // Provider
  provider: Provider;
  model: string;
  api_endpoint: string;

  // Params
  temperature: number | null;
  max_tokens: number | null;
  top_p: number | null;
  is_streaming: boolean;
  tool_choice: unknown;

  // Content
  system_prompt: string[] | string | null;
  messages: Message[];
  tools: ToolDefinition[];

  // Response
  response_messages: Message[];
  stop_reason: StopReason | null;
  usage: TokenUsage;
  status: RequestStatus;

  // Extras
  request_params: Record<string, unknown>;
  response_metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

export interface Session {
  id: string;
  name: string;
  started_at: string; // ISO-8601 datetime
  ended_at: string | null; // ISO-8601 datetime
  request_count: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

// ---------------------------------------------------------------------------
// Session stats
// ---------------------------------------------------------------------------

export interface SessionStats {
  total_requests: number;
  total_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  estimated_cost_usd: number;
  avg_duration_ms: number | null;
  avg_tokens_per_request: number | null;
  models_used: string[];
  providers_used: string[];
}

// ---------------------------------------------------------------------------
// Raw capture
// ---------------------------------------------------------------------------

export interface RawCapture {
  id: string;
  session_id: string;
  timestamp: string; // ISO-8601 datetime
  capture_mode: string;
  capture_label: string | null;
  capture_metadata: Record<string, unknown>;

  // Provider detection
  provider: Provider;

  // Request
  request_url: string;
  request_method: string;
  request_headers: Record<string, string>;
  request_body: Record<string, unknown> | string;

  // Response
  response_status: number;
  response_headers: Record<string, string>;
  response_body: Record<string, unknown> | string;

  // Streaming
  is_streaming: boolean;
  sse_events: Record<string, unknown>[];
}
