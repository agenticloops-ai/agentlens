"""CLI entry point for agentlens."""

import asyncio
import contextlib
import os
import signal
import webbrowser
from datetime import datetime
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agentlens.models import Session
from agentlens.providers import PluginRegistry
from agentlens.proxy.addon import AgentLensAddon
from agentlens.server.app import create_app
from agentlens.server.event_bus import EventBus
from agentlens.storage.database import init_db
from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
    SessionRepository,
)

app = typer.Typer(
    name="agentlens",
    help="Profile AI agents by intercepting LLM API traffic.",
)
console = Console()


@app.command()
def start(
    proxy_port: int = typer.Option(8080, help="Port for the MITM proxy"),
    web_port: int = typer.Option(8081, help="Port for the web UI"),
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    session_name: str = typer.Option("", help="Name for this profiling session"),
    db_path: str = typer.Option(
        str(Path.home() / ".agentlens" / "data.db"),
        help="Path to SQLite database",
    ),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open web UI in browser"),
):
    """Start the proxy and web UI."""
    asyncio.run(_start(proxy_port, web_port, host, session_name, db_path, open_browser))


async def _start(
    proxy_port: int,
    web_port: int,
    host: str,
    session_name: str,
    db_path: str,
    open_browser: bool,
) -> None:
    # Ensure DB directory exists
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    # Initialize database
    engine = await init_db(db_path)

    # Create repositories
    session_repo = SessionRepository(engine)
    request_repo = RequestRepository(engine)
    raw_capture_repo = RawCaptureRepository(engine)
    event_bus = EventBus()

    # Create session
    session = Session(
        name=session_name or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    )
    await session_repo.create(session)

    # Create proxy addon
    plugin_registry = PluginRegistry.default()
    addon = AgentLensAddon(
        session_id=session.id,
        session_repo=session_repo,
        request_repo=request_repo,
        raw_capture_repo=raw_capture_repo,
        event_bus=event_bus,
        parser_registry=plugin_registry,
    )

    # Create FastAPI app with lifespan disabled -- the CLI manages the
    # engine, repositories, and event bus lifecycle directly so that the
    # proxy addon and the web server share the exact same instances.
    os.environ["AGENT_PROFILER_DB_PATH"] = db_path
    web_app = create_app(skip_lifespan=True)
    web_app.state.engine = engine
    web_app.state.session_repo = session_repo
    web_app.state.request_repo = request_repo
    web_app.state.raw_capture_repo = raw_capture_repo
    web_app.state.event_bus = event_bus

    # Print startup banner
    _print_banner(host, proxy_port, web_port, session)

    # Start proxy
    from agentlens.proxy.runner import run_proxy

    proxy_master, proxy_task = await run_proxy(addon, host=host, port=proxy_port)

    # Open browser
    if open_browser:
        webbrowser.open(f"http://{host}:{web_port}")

    # Start web server (this blocks until shutdown)
    config = uvicorn.Config(
        web_app,
        host=host,
        port=web_port,
        log_level="warning",
        lifespan="off",  # CLI manages the lifecycle; skip ASGI lifespan protocol.
    )
    server = uvicorn.Server(config)

    # Handle graceful shutdown
    shutdown_event = asyncio.Event()
    # Mutable list so the signal handler can reach tasks defined later.
    _tasks: list[asyncio.Task] = []

    def _signal_handler():
        if shutdown_event.is_set():
            # Second signal — force-cancel running tasks so we don't hang.
            console.print("\n[red]Forced exit.[/red]")
            for t in _tasks:
                t.cancel()
            return
        console.print("\n[yellow]Shutting down...[/yellow]")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        # Start uvicorn in background
        server_task = asyncio.create_task(server.serve())
        _tasks.extend([server_task, proxy_task])

        # Wait for shutdown signal
        await shutdown_event.wait()

        # Finalize session
        session.ended_at = datetime.utcnow()
        await session_repo.update(session)

        # Shutdown: stop accepting new proxy connections first, then the
        # web server.  Await both tasks so mitmproxy's internal tasks
        # (connection handlers, timeout watchdog) get a chance to clean up
        # instead of being destroyed while still pending.
        proxy_master.shutdown()
        server.should_exit = True
        try:
            await asyncio.wait_for(
                asyncio.gather(server_task, proxy_task, return_exceptions=True),
                timeout=5,
            )
        except asyncio.TimeoutError:
            pass

    except (Exception, asyncio.CancelledError):
        pass
    finally:
        # Cancel any straggling tasks spawned by the proxy or addon.
        for task in _tasks:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await engine.dispose()
        console.print("[green]Session finalized. Goodbye![/green]")


def _print_banner(host: str, proxy_port: int, web_port: int, session: Session) -> None:
    """Print startup banner with configuration info."""
    banner = Text()
    banner.append("AgentLens", style="bold magenta")
    banner.append(" v0.1.0\n\n")
    banner.append("  Proxy:    ", style="dim")
    banner.append(f"http://{host}:{proxy_port}\n", style="bold cyan")
    banner.append("  Web UI:   ", style="dim")
    banner.append(f"http://{host}:{web_port}\n", style="bold cyan")
    banner.append("  Session:  ", style="dim")
    banner.append(f"{session.name}\n\n", style="bold")
    banner.append("Configure your agent:\n", style="dim")
    banner.append(f"  export HTTP_PROXY=http://{host}:{proxy_port}\n", style="green")
    banner.append(f"  export HTTPS_PROXY=http://{host}:{proxy_port}\n", style="green")
    banner.append(
        "  export REQUESTS_CA_BUNDLE=~/.mitmproxy/mitmproxy-ca-cert.pem\n",
        style="green",
    )
    banner.append("\nPress ", style="dim")
    banner.append("Ctrl+C", style="bold yellow")
    banner.append(" to stop.", style="dim")

    console.print(Panel(banner, border_style="magenta", padding=(1, 2)))


@app.command()
def replay():
    """Re-parse raw captures with updated parsers."""
    typer.echo("Not yet implemented")
    raise typer.Exit(1)


@app.command()
def export():
    """Export session to JSON."""
    typer.echo("Not yet implemented")
    raise typer.Exit(1)
