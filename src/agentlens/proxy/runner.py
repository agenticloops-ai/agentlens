"""Programmatic mitmproxy launcher."""

import asyncio

from mitmproxy.options import Options
from mitmproxy.tools.dump import DumpMaster

from agentlens.proxy.addon import AgentLensAddon


async def run_proxy(
    addon: AgentLensAddon,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> tuple[DumpMaster, asyncio.Task]:
    """Start mitmproxy programmatically with our addon.

    Returns the master and its background task so the caller can await
    the task during shutdown.
    """
    opts = Options(
        listen_host=host,
        listen_port=port,
        ssl_insecure=True,  # Don't verify upstream TLS (since we're intercepting)
    )
    master = DumpMaster(opts)
    master.addons.add(addon)

    # Run in background — keep a reference so we can await it on shutdown.
    task = asyncio.create_task(master.run(), name="mitmproxy-master")
    return master, task
