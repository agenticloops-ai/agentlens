"""Capture helpers for explicit and transparent interception modes."""

from .pf import PF_ANCHOR_NAME, build_pf_rules, clear_anchor, default_pf_user, disable_pf, enable_pf, load_anchor
from .redaction import redact_headers, redact_payload
from .targets import detect_default_interface, resolve_target_ips

__all__ = [
    "PF_ANCHOR_NAME",
    "build_pf_rules",
    "clear_anchor",
    "default_pf_user",
    "detect_default_interface",
    "disable_pf",
    "enable_pf",
    "load_anchor",
    "redact_headers",
    "redact_payload",
    "resolve_target_ips",
]
