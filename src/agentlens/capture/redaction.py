"""Helpers for redacting secrets before persistence."""

from __future__ import annotations

from typing import Any


_REDACTED = "REDACTED"
_HEADER_KEYS = {
    "authorization",
    "x-api-key",
    "proxy-authorization",
    "cookie",
    "set-cookie",
}
_BODY_KEYS = {
    "api_key",
    "access_token",
    "token",
    "authorization",
}


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key: (_REDACTED if key.lower() in _HEADER_KEYS else value) for key, value in headers.items()}


def redact_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            if key.lower() in _BODY_KEYS:
                redacted[key] = _REDACTED
            else:
                redacted[key] = redact_payload(value)
        return redacted
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    return payload
