"""Raw capture model — stores unprocessed HTTP request/response data."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class RawCapture(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    capture_mode: str = "explicit_proxy"
    capture_label: str | None = None
    capture_metadata: dict[str, Any] = Field(default_factory=dict)

    # Provider detection
    provider: str = "unknown"

    # Request
    request_url: str = ""
    request_method: str = "POST"
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: dict[str, Any] | str = Field(default_factory=dict)

    # Response
    response_status: int = 0
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: dict[str, Any] | str = Field(default_factory=dict)

    # Streaming
    is_streaming: bool = False
    sse_events: list[dict[str, Any]] = Field(default_factory=list)
