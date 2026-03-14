"""macOS PF helpers for transparent interception."""

from __future__ import annotations

import os
import pwd
import re
import subprocess
from pathlib import Path


PF_ANCHOR_NAME = "com.apple/agentlens_transparent"
_PF_TOKEN_RE = re.compile(r"Token\s*:\s*(?P<token>\d+)")


def build_pf_rules(*, interface: str, target_ips: list[str], listen_host: str, listen_port: int, pf_user: str) -> str:
    if target_ips:
        dest = "{" + ", ".join(target_ips) + "}"
    else:
        dest = "any"
    lines = [
        f"rdr on lo0 inet proto tcp from any to {dest} port 443 -> {listen_host} port {listen_port}",
        f"pass out on {interface} route-to lo0 inet proto tcp from any to {dest} port 443 user {pf_user}",
    ]
    return "\n".join(lines) + "\n"


def _run(command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, input=input_text)


def _parse_pf_token(output: str) -> str | None:
    match = _PF_TOKEN_RE.search(output)
    return match.group("token") if match else None


def default_pf_user() -> str:
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        return sudo_user
    return pwd.getpwuid(os.getuid()).pw_name


def enable_pf() -> str:
    result = _run(["/sbin/pfctl", "-E"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "pfctl -E failed")
    token = _parse_pf_token(result.stdout + result.stderr)
    if not token:
        raise RuntimeError("Could not parse PF token from pfctl output.")
    return token


def load_anchor(anchor_file: Path) -> None:
    result = _run(["/sbin/pfctl", "-a", PF_ANCHOR_NAME, "-f", str(anchor_file)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "pfctl anchor load failed")


def clear_anchor() -> None:
    _run(["/sbin/pfctl", "-a", PF_ANCHOR_NAME, "-F", "all"])


def disable_pf(token: str) -> None:
    _run(["/sbin/pfctl", "-X", token])
