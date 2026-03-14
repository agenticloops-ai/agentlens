from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "src" / "agentlens" / "capture" / "pf.py"
    spec = importlib.util.spec_from_file_location("agentlens_capture_pf", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_pf_rules_scopes_redirect_to_targets_and_user() -> None:
    module = _load_module()

    rules = module.build_pf_rules(
        interface="en0",
        target_ips=["160.79.104.10", "34.149.66.137"],
        listen_host="127.0.0.1",
        listen_port=8899,
        pf_user="alx",
    )

    assert "rdr on lo0" in rules
    assert "160.79.104.10, 34.149.66.137" in rules
    assert "pass out on en0 route-to lo0" in rules
    assert "user alx" in rules
    assert "-> 127.0.0.1 port 8899" in rules
