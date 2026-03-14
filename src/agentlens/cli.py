"""CLI entry point for agentlens."""

from __future__ import annotations

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
from rich.text import Text

from agentlens import __version__
from agentlens.capture import (
    build_pf_rules,
    clear_anchor,
    default_pf_user,
    detect_default_interface,
    disable_pf,
    enable_pf,
    load_anchor,
    resolve_target_ips,
)
from agentlens.capture.transparent import (
    build_capture_metadata,
    default_confdir,
    ensure_ca_cert,
    ensure_ip_forwarding,
    require_transparent_support,
)
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

_DEFAULT_DB_PATH = str(Path.home() / ".agentlens" / "data.db")
_MITMPROXY_CA_CERT = str(Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_export_summary(written: list[Path]) -> None:
    """Print a summary of exported files."""
    if not written:
        console.print("[yellow]No files exported.[/yellow]")
        return

    console.print()
    console.print("[bold green]Exported files:[/bold green]")
    for p in written:
        console.print(f"  {p}", style="dim")
    console.print()


# ---------------------------------------------------------------------------
# start — original command (proxy + web UI)
# ---------------------------------------------------------------------------


@app.command()
def start(
    proxy_port: int = typer.Option(8080, help="Port for the MITM proxy"),
    web_port: int = typer.Option(8081, help="Port for the web UI"),
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    session_name: str = typer.Option("", help="Name for this profiling session"),
    db_path: str = typer.Option(_DEFAULT_DB_PATH, help="Path to SQLite database"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open web UI in browser"),
):
    """Start the proxy and web UI."""
    asyncio.run(_start(proxy_port, web_port, host, session_name, db_path, open_browser))


@app.command()
def capture(
    mode: str = typer.Option("explicit_proxy", help="Capture mode: explicit_proxy or transparent"),
    proxy_port: int = typer.Option(8080, help="Port for the capture listener"),
    web_port: int = typer.Option(8081, help="Port for the web UI"),
    host: str = typer.Option("127.0.0.1", help="Host to bind the web UI to"),
    session_name: str = typer.Option("", help="Name for this profiling session"),
    db_path: str = typer.Option(_DEFAULT_DB_PATH, help="Path to SQLite database"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open web UI in browser"),
    target_host: list[str] = typer.Option([], "--target-host", help="Transparent capture target host"),
    target_ip: list[str] = typer.Option([], "--target-ip", help="Transparent capture target IP"),
    label: str = typer.Option("", help="Optional label for this capture mode"),
    pf_user: str = typer.Option("", help="Redirect only traffic owned by this local user"),
):
    """Start a capture session using either explicit proxy or transparent interception."""
    if mode == "explicit_proxy":
        asyncio.run(_start(proxy_port, web_port, host, session_name, db_path, open_browser))
        return
    if mode != "transparent":
        console.print(f"[red]Unsupported capture mode: {mode}[/red]")
        raise typer.Exit(1)
    asyncio.run(
        _start_transparent(
            proxy_port=proxy_port,
            web_port=web_port,
            host=host,
            session_name=session_name,
            db_path=db_path,
            open_browser=open_browser,
            target_hosts=target_host,
            target_ips=target_ip,
            capture_label=label or None,
            pf_user=pf_user or default_pf_user(),
        )
    )


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

    # End any stale active sessions left over from a previous unclean shutdown
    await session_repo.end_all_active()

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
    web_app.state.addon = addon

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


def _display_host(host: str) -> str:
    """Return a browser-friendly host (0.0.0.0 → 127.0.0.1)."""
    return "127.0.0.1" if host == "0.0.0.0" else host


def _print_banner(host: str, proxy_port: int, web_port: int, session: Session) -> None:
    """Print startup banner with configuration info."""
    host = _display_host(host)
    banner = Text()
    banner.append("AgentLens", style="bold magenta")
    banner.append(f" v{__version__}\n\n")
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

    console.print()
    console.print(banner)
    console.print()


def _print_transparent_banner(
    *,
    web_host: str,
    web_port: int,
    proxy_port: int,
    session: Session,
    capture_label: str | None,
    target_hosts: list[str],
    target_ips: list[str],
) -> None:
    display = _display_host(web_host)
    banner = Text()
    banner.append("AgentLens", style="bold magenta")
    banner.append(f" v{__version__}\n\n")
    banner.append("  Mode:     ", style="dim")
    banner.append("transparent\n", style="bold cyan")
    banner.append("  Web UI:   ", style="dim")
    banner.append(f"http://{display}:{web_port}\n", style="bold cyan")
    banner.append("  Proxy:    ", style="dim")
    banner.append(f"127.0.0.1:{proxy_port}\n", style="bold cyan")
    banner.append("  Session:  ", style="dim")
    banner.append(f"{session.name}\n", style="bold")
    if capture_label:
        banner.append("  Label:    ", style="dim")
        banner.append(f"{capture_label}\n", style="bold")
    banner.append("  Targets:  ", style="dim")
    if target_hosts or target_ips:
        banner.append(", ".join(target_hosts or target_ips) + "\n\n", style="bold")
    else:
        banner.append("all port 443 traffic\n\n", style="bold")
    banner.append("Transparent interception is active via PF.\n", style="dim")
    banner.append("Press ", style="dim")
    banner.append("Ctrl+C", style="bold yellow")
    banner.append(" to stop.", style="dim")
    console.print()
    console.print(banner)
    console.print()


async def _start_transparent(
    *,
    proxy_port: int,
    web_port: int,
    host: str,
    session_name: str,
    db_path: str,
    open_browser: bool,
    target_hosts: list[str],
    target_ips: list[str],
    capture_label: str | None,
    pf_user: str,
) -> None:
    try:
        require_transparent_support()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    resolved_target_ips = resolve_target_ips(target_hosts=target_hosts, target_ips=target_ips)

    interface = detect_default_interface()
    confdir = default_confdir()
    try:
        ensure_ca_cert(confdir)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    ensure_ip_forwarding()

    anchor_dir = Path("/tmp") / f"agentlens-transparent-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    anchor_dir.mkdir(parents=True, exist_ok=True)
    anchor_path = anchor_dir / "pf-anchor.conf"
    anchor_path.write_text(
        build_pf_rules(
            interface=interface,
            target_ips=resolved_target_ips,
            listen_host="127.0.0.1",
            listen_port=proxy_port,
            pf_user=pf_user,
        ),
        encoding="utf-8",
    )

    pf_token = ""
    engine = None
    _tasks: list[asyncio.Task] = []
    try:
        pf_token = enable_pf()
        load_anchor(anchor_path)

        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        engine = await init_db(db_path)
        session_repo = SessionRepository(engine)
        request_repo = RequestRepository(engine)
        raw_capture_repo = RawCaptureRepository(engine)
        event_bus = EventBus()

        await session_repo.end_all_active()
        session = Session(name=session_name or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        await session_repo.create(session)

        plugin_registry = PluginRegistry.default()
        addon = AgentLensAddon(
            session_id=session.id,
            session_repo=session_repo,
            request_repo=request_repo,
            raw_capture_repo=raw_capture_repo,
            event_bus=event_bus,
            parser_registry=plugin_registry,
            capture_mode="transparent",
            capture_label=capture_label,
            capture_metadata_factory=build_capture_metadata,
        )

        os.environ["AGENT_PROFILER_DB_PATH"] = db_path
        web_app = create_app(skip_lifespan=True)
        web_app.state.engine = engine
        web_app.state.session_repo = session_repo
        web_app.state.request_repo = request_repo
        web_app.state.raw_capture_repo = raw_capture_repo
        web_app.state.event_bus = event_bus
        web_app.state.addon = addon

        _print_transparent_banner(
            web_host=host,
            web_port=web_port,
            proxy_port=proxy_port,
            session=session,
            capture_label=capture_label,
            target_hosts=target_hosts,
            target_ips=resolved_target_ips,
        )

        from agentlens.proxy.runner import run_proxy

        proxy_master, proxy_task = await run_proxy(
            addon,
            host="127.0.0.1",
            port=proxy_port,
            mode="transparent",
            confdir=str(confdir),
        )

        if open_browser:
            webbrowser.open(f"http://{host}:{web_port}")

        config = uvicorn.Config(
            web_app,
            host=host,
            port=web_port,
            log_level="warning",
            lifespan="off",
        )
        server = uvicorn.Server(config)

        shutdown_event = asyncio.Event()

        def _signal_handler():
            if shutdown_event.is_set():
                console.print("\n[red]Forced exit.[/red]")
                for task in _tasks:
                    task.cancel()
                return
            console.print("\n[yellow]Shutting down...[/yellow]")
            shutdown_event.set()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

        try:
            server_task = asyncio.create_task(server.serve())
            _tasks.extend([server_task, proxy_task])
            await shutdown_event.wait()
            session.ended_at = datetime.utcnow()
            await session_repo.update(session)
            proxy_master.shutdown()
            server.should_exit = True
            try:
                await asyncio.wait_for(
                    asyncio.gather(server_task, proxy_task, return_exceptions=True),
                    timeout=5,
                )
            except asyncio.TimeoutError:
                pass
        finally:
            for task in _tasks:
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
    finally:
        clear_anchor()
        if pf_token:
            disable_pf(pf_token)
        if engine is not None:
            await engine.dispose()
        console.print("[green]Session finalized. Goodbye![/green]")


# ---------------------------------------------------------------------------
# wait — human-in-the-loop capture: start proxy, wait for Ctrl+C, export
# ---------------------------------------------------------------------------


@app.command()
def wait(
    output: str = typer.Option("results", help="Output directory for exported files"),
    formats: str = typer.Option("json,markdown,csv", help="Comma-separated export formats"),
    session_name: str = typer.Option("", help="Override auto-generated session name"),
    proxy_port: int = typer.Option(8080, help="Port for the MITM proxy"),
    web_port: int = typer.Option(8081, help="Port for the web UI"),
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    db_path: str = typer.Option(_DEFAULT_DB_PATH, help="Path to SQLite database"),
    web: bool = typer.Option(True, "--web/--no-web", help="Start web UI alongside proxy"),
    open_browser: bool = typer.Option(False, "--open/--no-open", help="Open web UI in browser"),
):
    """Start proxy and wait for Ctrl+C, then export results.

    Example: agentlens wait --output results/claude-codegen --web --open
    """
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    name = session_name or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    fmt_list = [f.strip() for f in formats.split(",") if f.strip()]
    dest = Path(output) / timestamp

    asyncio.run(
        _wait(
            session_name=name,
            output_dir=dest,
            formats=fmt_list,
            proxy_port=proxy_port,
            web_port=web_port,
            host=host,
            db_path=db_path,
            web=web,
            open_browser=open_browser,
        )
    )


async def _wait(
    *,
    session_name: str,
    output_dir: Path,
    formats: list[str],
    proxy_port: int,
    web_port: int,
    host: str,
    db_path: str,
    web: bool,
    open_browser: bool,
) -> None:
    from agentlens.runner import headless_proxy

    async with headless_proxy(
        session_name=session_name,
        proxy_port=proxy_port,
        host=host,
        db_path=db_path,
    ) as ctx:
        # Print wait banner
        display = _display_host(host)
        proxy_url = f"http://{display}:{proxy_port}"
        banner = Text()
        banner.append("AgentLens", style="bold magenta")
        banner.append(" wait\n\n")
        banner.append("  Proxy:    ", style="dim")
        banner.append(f"{proxy_url}\n", style="bold cyan")
        if web:
            banner.append("  Web UI:   ", style="dim")
            banner.append(f"http://{display}:{web_port}\n", style="bold cyan")
        banner.append("  Session:  ", style="dim")
        banner.append(f"{ctx.session.name}\n\n", style="bold")
        banner.append("Configure your agent:\n", style="dim")
        banner.append(f"  export HTTP_PROXY={proxy_url}\n", style="green")
        banner.append(f"  export HTTPS_PROXY={proxy_url}\n", style="green")
        banner.append(f"  export REQUESTS_CA_BUNDLE={_MITMPROXY_CA_CERT}\n", style="green")
        banner.append(f"  export SSL_CERT_FILE={_MITMPROXY_CA_CERT}\n", style="green")
        banner.append(f"  export NODE_EXTRA_CA_CERTS={_MITMPROXY_CA_CERT}\n", style="green")
        banner.append("\nPress ", style="dim")
        banner.append("Ctrl+C", style="bold yellow")
        banner.append(" to stop and export.", style="dim")
        console.print()
        console.print(banner)
        console.print()

        # Optionally start web UI
        web_server = None
        if web:
            web_server = await _start_web_server(ctx, db_path, host, web_port)
            if open_browser:
                webbrowser.open(f"http://{host}:{web_port}")

        # Wait for Ctrl+C
        shutdown_event = asyncio.Event()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_event.set)

        await shutdown_event.wait()
        console.print("\n[yellow]Stopping capture...[/yellow]")

        # Ignore further SIGINTs during shutdown to prevent asyncio cleanup hang
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        # Brief sleep for in-flight responses
        await asyncio.sleep(2)

        if web_server:
            web_server.should_exit = True

    # Export results
    from agentlens.export.writer import export_session_to_dir

    engine = await init_db(db_path)
    session_repo = SessionRepository(engine)
    request_repo = RequestRepository(engine)
    raw_capture_repo = RawCaptureRepository(engine)

    try:
        written = await export_session_to_dir(
            ctx.session.id,
            output_dir,
            session_repo=session_repo,
            request_repo=request_repo,
            raw_capture_repo=raw_capture_repo,
            formats=formats,
        )
        _print_export_summary(written)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# export — export an existing session from the database
# ---------------------------------------------------------------------------


@app.command()
def export(
    session_identifier: str = typer.Argument(help="Session ID or session name"),
    output_dir: str = typer.Option("exports", help="Output directory"),
    formats: str = typer.Option("json,markdown,csv", help="Comma-separated export formats"),
    db_path: str = typer.Option(_DEFAULT_DB_PATH, help="Path to SQLite database"),
):
    """Export a session from the database by ID or name."""
    fmt_list = [f.strip() for f in formats.split(",") if f.strip()]
    asyncio.run(_export(session_identifier, Path(output_dir), fmt_list, db_path))


async def _export(
    session_identifier: str,
    output_dir: Path,
    formats: list[str],
    db_path: str,
) -> None:
    from agentlens.export.writer import export_session_to_dir

    engine = await init_db(db_path)
    session_repo = SessionRepository(engine)
    request_repo = RequestRepository(engine)
    raw_capture_repo = RawCaptureRepository(engine)

    try:
        # Try by ID first, then by name
        session = await session_repo.get(session_identifier)
        if session is None:
            session = await session_repo.get_by_name(session_identifier)
        if session is None:
            console.print(f"[red]Session not found: {session_identifier}[/red]")
            raise typer.Exit(1)

        written = await export_session_to_dir(
            session.id,
            output_dir,
            session_repo=session_repo,
            request_repo=request_repo,
            raw_capture_repo=raw_capture_repo,
            formats=formats,
        )
        _print_export_summary(written)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# replay — placeholder
# ---------------------------------------------------------------------------


@app.command()
def replay():
    """Re-parse raw captures with updated parsers."""
    typer.echo("Not yet implemented")
    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Shared: web server helper for run/wait
# ---------------------------------------------------------------------------


async def _start_web_server(
    ctx,
    db_path: str,
    host: str,
    web_port: int = 8081,
) -> uvicorn.Server:
    """Start a uvicorn web server in the background for run/wait commands."""
    os.environ["AGENT_PROFILER_DB_PATH"] = db_path
    web_app = create_app(skip_lifespan=True)

    # Re-init engine for the web app since it needs its own connection
    engine = await init_db(db_path)
    web_app.state.engine = engine
    web_app.state.session_repo = SessionRepository(engine)
    web_app.state.request_repo = RequestRepository(engine)
    web_app.state.raw_capture_repo = RawCaptureRepository(engine)
    web_app.state.event_bus = ctx.event_bus

    config = uvicorn.Config(
        web_app,
        host=host,
        port=web_port,
        log_level="warning",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())
    return server
