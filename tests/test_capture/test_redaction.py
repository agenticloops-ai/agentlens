from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "src" / "agentlens" / "capture" / "redaction.py"
    spec = importlib.util.spec_from_file_location("agentlens_capture_redaction", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_redact_headers_masks_sensitive_values() -> None:
    module = _load_module()
    headers = {
        "Authorization": "Bearer secret",
        "x-api-key": "sk-ant-secret",
        "content-type": "application/json",
    }

    redacted = module.redact_headers(headers)

    assert redacted["Authorization"] == "REDACTED"
    assert redacted["x-api-key"] == "REDACTED"
    assert redacted["content-type"] == "application/json"


def test_redact_payload_masks_nested_token_fields() -> None:
    module = _load_module()
    payload = {
        "messages": [{"role": "user", "content": "hello"}],
        "token": "abc",
        "nested": {"access_token": "xyz"},
    }

    redacted = module.redact_payload(payload)

    assert redacted["token"] == "REDACTED"
    assert redacted["nested"]["access_token"] == "REDACTED"
    assert redacted["messages"][0]["content"] == "hello"
