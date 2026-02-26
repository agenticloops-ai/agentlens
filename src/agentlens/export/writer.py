"""File-based session exporter for CLI use."""

from __future__ import annotations

from pathlib import Path

from agentlens.export.formats import (
    render_csv,
    render_json,
    render_markdown,
    safe_filename,
)
from agentlens.storage.repositories import (
    RawCaptureRepository,
    RequestRepository,
    SessionRepository,
)

VALID_FORMATS = {"json", "markdown", "csv"}
DEFAULT_FORMATS = ["json", "markdown", "csv"]


async def export_session_to_dir(
    session_id: str,
    output_dir: Path,
    *,
    session_repo: SessionRepository,
    request_repo: RequestRepository,
    raw_capture_repo: RawCaptureRepository,
    formats: list[str] | None = None,
) -> list[Path]:
    """Export a session to files in *output_dir*.

    Returns the list of written file paths.
    """
    formats = formats or DEFAULT_FORMATS

    session = await session_repo.get(session_id)
    if session is None:
        msg = f"Session {session_id} not found"
        raise ValueError(msg)

    stats = await session_repo.get_stats(session_id)
    requests = await request_repo.list_by_session(session_id, limit=10_000)
    basename = safe_filename(session.name)

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for fmt in formats:
        if fmt == "json":
            raw_captures = []
            for req in requests:
                if req.raw_capture_id:
                    capture = await raw_capture_repo.get(req.raw_capture_id)
                    if capture is not None:
                        raw_captures.append(capture.model_dump(mode="json"))
            content = render_json(session, stats, requests, raw_captures)
            path = output_dir / f"{basename}.json"
        elif fmt == "markdown":
            content = render_markdown(session, stats, requests)
            path = output_dir / f"{basename}.md"
        elif fmt == "csv":
            content = render_csv(requests)
            path = output_dir / f"{basename}.csv"
        else:
            continue

        path.write_text(content, encoding="utf-8")
        written.append(path)

    return written
