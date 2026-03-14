"""mitmproxy addon for intercepting and profiling LLM API traffic."""

from __future__ import annotations

import asyncio
import gzip
import json
import time
import zlib
from collections.abc import Callable

from mitmproxy import http

from agentlens.capture.redaction import redact_headers, redact_payload
from agentlens.models import RawCapture
from agentlens.providers import PluginRegistry


class AgentLensAddon:
    """mitmproxy addon that captures LLM API requests and responses."""

    def __init__(
        self,
        session_id: str,
        session_repo,
        request_repo,
        raw_capture_repo,
        event_bus,
        parser_registry=None,
        capture_mode: str = "explicit_proxy",
        capture_label: str | None = None,
        capture_metadata_factory: Callable[[http.HTTPFlow], dict] | None = None,
    ):
        self.session_id = session_id
        self.session_repo = session_repo
        self.request_repo = request_repo
        self.raw_capture_repo = raw_capture_repo
        self.event_bus = event_bus
        self.registry = parser_registry or PluginRegistry.default()
        self.capture_mode = capture_mode
        self.capture_label = capture_label
        self.capture_metadata_factory = capture_metadata_factory
        self._request_times: dict[str, float] = {}  # flow.id -> start time
        self._ttft_times: dict[str, float] = {}  # flow.id -> time to first token
        self._stream_buffers: dict[str, list[bytes]] = {}  # flow.id -> accumulated chunks

    def requestheaders(self, flow: http.HTTPFlow):
        """Called when request headers are received."""
        host = flow.request.headers.get("host", flow.request.pretty_host)
        path = flow.request.path
        headers = dict(flow.request.headers)

        if not self.registry.is_llm_request(host, path, headers):
            return  # Skip non-LLM traffic

        # Force JSON responses for Cloud Code API (defaults to protobuf).
        if "cloudcode-pa.googleapis.com" in host:
            if "alt=" not in flow.request.path:
                separator = "&" if "?" in flow.request.path else "?"
                flow.request.path += f"{separator}alt=json"
            flow.request.headers["accept"] = "application/json"

        # Tell the upstream server not to compress — the stream callback
        # captures raw wire bytes so we'd get gzip/br data instead of text.
        flow.request.headers["accept-encoding"] = "identity"

        # Mark this flow for capture
        flow.metadata["capture"] = True
        flow.metadata["provider"] = self.registry.detect_provider(host, path, headers)
        self._request_times[flow.id] = time.time()

    def responseheaders(self, flow: http.HTTPFlow):
        """Called when response headers are received."""
        if not flow.metadata.get("capture"):
            # Enable streaming for non-captured flows so mitmproxy passes
            # them through without buffering.  This prevents timeouts for
            # SSE / streaming connections to non-LLM endpoints.
            flow.response.stream = True
            return

        # Always stream captured flows through to the client while
        # accumulating chunks.  Some endpoints (e.g. Codex via chatgpt.com)
        # send SSE without a text/event-stream Content-Type, and the
        # Responses API may stream without "stream": true in the body.
        # Buffering these causes client timeouts / disconnects.  We detect
        # whether the response is actually SSE later, in response(), from
        # the accumulated data.
        chunks: list[bytes] = []
        self._stream_buffers[flow.id] = chunks

        def _capture(data: bytes) -> bytes:
            chunks.append(data)
            return data

        flow.response.stream = _capture

        # Best-effort streaming hint for TTFT measurement.
        content_type = flow.response.headers.get("content-type", "")
        is_streaming = "text/event-stream" in content_type

        if not is_streaming:
            try:
                req_body = json.loads(flow.request.get_text())
                if isinstance(req_body, dict) and req_body.get("stream") is True:
                    is_streaming = True
            except (json.JSONDecodeError, ValueError):
                pass

        flow.metadata["is_streaming"] = is_streaming

        if is_streaming:
            self._ttft_times[flow.id] = time.time()

    def response(self, flow: http.HTTPFlow):
        """Called when full response is received."""
        if not flow.metadata.get("capture"):
            return

        # Calculate timing
        start_time = self._request_times.pop(flow.id, None)
        duration_ms = (time.time() - start_time) * 1000 if start_time else None
        ttft_time = self._ttft_times.pop(flow.id, None)
        ttft_ms = (ttft_time - start_time) * 1000 if ttft_time and start_time else None

        provider = flow.metadata.get("provider", "unknown")
        is_streaming = flow.metadata.get("is_streaming", False)

        # Build request body
        try:
            request_body = json.loads(flow.request.get_text())
        except (json.JSONDecodeError, ValueError):
            request_body = flow.request.get_text()

        # Always read from the accumulated buffer — flow.response body is
        # empty when we use a streaming callback (which we always do for
        # captured flows now).
        buf = self._stream_buffers.pop(flow.id, [])
        raw_bytes = b"".join(buf)

        # Decompress if the server sent compressed data despite our
        # accept-encoding: identity header.
        raw_bytes = self._decompress(raw_bytes, flow.response.headers.get("content-encoding", ""))

        response_text = raw_bytes.decode("utf-8", errors="replace")

        # Detect SSE from the actual content when the header/body hints
        # missed it (e.g. Codex via chatgpt.com sends SSE without
        # Content-Type: text/event-stream).
        if not is_streaming and self._looks_like_sse(response_text):
            is_streaming = True

        # Build response body and SSE events
        sse_events = []
        response_body = {}

        if is_streaming:
            sse_events = self._split_sse(response_text)
            response_body = ""
        else:
            try:
                response_body = json.loads(response_text)
            except (json.JSONDecodeError, ValueError):
                response_body = response_text

        capture_metadata = {}
        if self.capture_metadata_factory is not None:
            capture_metadata.update(self.capture_metadata_factory(flow))
        capture_metadata.update(self._partial_response_metadata(flow, raw_bytes))

        # Build RawCapture
        raw = RawCapture(
            session_id=self.session_id,
            capture_mode=self.capture_mode,
            capture_label=self.capture_label,
            capture_metadata=capture_metadata,
            provider=provider or "unknown",
            request_url=self._canonical_request_url(flow),
            request_method=flow.request.method,
            request_headers=redact_headers({k: v for k, v in flow.request.headers.items()}),
            request_body=redact_payload(request_body),
            response_status=flow.response.status_code,
            response_headers=redact_headers({k: v for k, v in flow.response.headers.items()}),
            response_body=redact_payload(response_body),
            is_streaming=is_streaming,
            sse_events=sse_events,
        )

        # Store and parse asynchronously
        asyncio.ensure_future(self._process_capture(raw, duration_ms, ttft_ms))

    async def _process_capture(self, raw: RawCapture, duration_ms: float | None, ttft_ms: float | None):
        """Store raw capture, parse it, store parsed request, publish event."""
        try:
            # Store raw
            await self.raw_capture_repo.create(raw)

            # Parse
            plugin = self.registry.get_plugin(raw)
            if plugin:
                llm_request = plugin.parse(raw, duration_ms=duration_ms, ttft_ms=ttft_ms)
                llm_request.session_id = self.session_id
                llm_request.raw_capture_id = raw.id
                llm_request.capture_mode = raw.capture_mode
                llm_request.capture_label = raw.capture_label
                llm_request.capture_metadata = dict(raw.capture_metadata)

                # Store parsed
                await self.request_repo.create(llm_request)

                # Update session stats atomically (avoids read-modify-write race)
                await self.session_repo.increment_stats(
                    self.session_id,
                    request_count=1,
                    total_tokens=llm_request.usage.total_tokens,
                    estimated_cost_usd=llm_request.usage.estimated_cost_usd or 0,
                )

                # Publish event
                await self.event_bus.publish(
                    {
                        "type": "new_request",
                        "data": {
                            "id": llm_request.id,
                            "session_id": llm_request.session_id,
                            "provider": llm_request.provider,
                            "model": llm_request.model,
                            "timestamp": llm_request.timestamp.isoformat(),
                            "duration_ms": llm_request.duration_ms,
                            "is_streaming": llm_request.is_streaming,
                            "status": llm_request.status,
                            "capture_mode": llm_request.capture_mode,
                            "capture_label": llm_request.capture_label,
                            "usage": llm_request.usage.model_dump(),
                        },
                    }
                )
        except Exception:
            import traceback

            traceback.print_exc()

    def error(self, flow: http.HTTPFlow):
        """Handle connection failures."""
        self._request_times.pop(flow.id, None)
        self._ttft_times.pop(flow.id, None)
        self._stream_buffers.pop(flow.id, None)

    @staticmethod
    def _decompress(data: bytes, content_encoding: str) -> bytes:
        """Decompress response bytes based on Content-Encoding header."""
        encoding = content_encoding.strip().lower()
        if not encoding or encoding == "identity":
            return data
        try:
            if encoding == "gzip":
                return gzip.decompress(data)
            if encoding == "deflate":
                return zlib.decompress(data)
            if encoding == "br":
                import brotli

                return brotli.decompress(data)
        except Exception:
            pass
        return data

    @staticmethod
    def _looks_like_sse(text: str) -> bool:
        """Heuristic: does this response body look like an SSE stream?"""
        if not text:
            return False
        # Check the first non-empty line for SSE markers.
        for line in text.split("\n", 10):
            stripped = line.strip()
            if not stripped:
                continue
            return stripped.startswith(("event:", "data:", ": "))
        return False

    @staticmethod
    def _split_sse(body: str) -> list[dict]:
        """Split an SSE response body into individual events."""
        events = []
        current_event = {}

        for line in body.split("\n"):
            line = line.strip()

            if not line:
                if current_event:
                    # Parse the data field if it's JSON
                    if "data" in current_event and current_event["data"] != "[DONE]":
                        try:
                            current_event["data"] = json.loads(current_event["data"])
                        except (json.JSONDecodeError, ValueError):
                            pass
                    events.append(current_event)
                    current_event = {}
                continue

            if line.startswith("event:"):
                current_event["event"] = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
                if "data" in current_event:
                    current_event["data"] += data
                else:
                    current_event["data"] = data
            elif line.startswith(":"):
                # Comment, skip
                continue

        # Handle last event if no trailing newline
        if current_event:
            if "data" in current_event and current_event["data"] != "[DONE]":
                try:
                    current_event["data"] = json.loads(current_event["data"])
                except (json.JSONDecodeError, ValueError):
                    pass
            events.append(current_event)

        return events

    @staticmethod
    def _canonical_request_url(flow: http.HTTPFlow) -> str:
        host = flow.request.headers.get("host")
        if host:
            return f"{flow.request.scheme}://{host}{flow.request.path}"
        return flow.request.pretty_url

    @staticmethod
    def _partial_response_metadata(flow: http.HTTPFlow, raw_bytes: bytes) -> dict[str, str | bool]:
        content_length = flow.response.headers.get("content-length", "").strip()
        if not content_length.isdigit():
            return {}
        expected_bytes = int(content_length)
        actual_bytes = len(raw_bytes)
        if actual_bytes >= expected_bytes:
            return {}
        return {
            "partial_response": True,
            "partial_response_reason": f"incomplete body: received {actual_bytes} of {expected_bytes} bytes",
        }
