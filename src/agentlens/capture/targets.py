"""Helpers for resolving interception targets."""

from __future__ import annotations

import re
import shutil
import socket
import subprocess


_ROUTE_INTERFACE_RE = re.compile(r"^\s*interface:\s+(?P<name>\S+)\s*$", re.MULTILINE)


def detect_default_interface() -> str:
    route_bin = shutil.which("route") or "/sbin/route"
    result = subprocess.run(
        [route_bin, "-n", "get", "default"],
        check=False,
        capture_output=True,
        text=True,
    )
    match = _ROUTE_INTERFACE_RE.search(result.stdout)
    if not match:
        raise RuntimeError("Could not determine the default network interface.")
    return match.group("name")


def resolve_target_ips(*, target_hosts: list[str], target_ips: list[str]) -> list[str]:
    resolved: set[str] = {ip for ip in target_ips if ip}
    for host in target_hosts:
        try:
            infos = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
        except socket.gaierror:
            continue
        for info in infos:
            address = info[4][0]
            if address:
                resolved.add(address)
    return sorted(resolved)
