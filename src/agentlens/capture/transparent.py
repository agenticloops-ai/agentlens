"""Transparent capture utilities."""

from __future__ import annotations

import os
import pwd
import subprocess
from pathlib import Path

from mitmproxy import http


def require_transparent_support() -> None:
    if os.uname().sysname != "Darwin":
        raise RuntimeError("Transparent capture is currently supported on macOS only.")
    if os.geteuid() != 0:
        raise RuntimeError("Transparent capture must be run with sudo/root privileges.")


def default_confdir() -> Path:
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        return Path(pwd.getpwnam(sudo_user).pw_dir) / ".mitmproxy"
    return Path.home() / ".mitmproxy"


def ensure_ca_cert(confdir: Path) -> Path:
    cert = confdir / "mitmproxy-ca-cert.pem"
    if not cert.exists():
        raise RuntimeError(f"mitmproxy CA certificate not found: {cert}")
    return cert


def ensure_ip_forwarding() -> None:
    subprocess.run(
        ["/usr/sbin/sysctl", "-w", "net.inet.ip.forwarding=1"],
        check=False,
        capture_output=True,
        text=True,
    )


def build_capture_metadata(flow: http.HTTPFlow) -> dict[str, str]:
    metadata = {"transport": "pf_redirect"}
    host_header = flow.request.headers.get("host")
    if host_header:
        metadata["requested_host"] = host_header
    server_address = getattr(flow.server_conn, "address", None)
    if server_address:
        metadata["upstream_ip"] = str(server_address[0])
    return metadata
