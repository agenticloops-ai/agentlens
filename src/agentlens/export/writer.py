"""File-based session exporter for CLI use."""

from __future__ import annotations

import json
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

VALID_FORMATS = {"json", "markdown", "csv", "raw"}
DEFAULT_FORMATS = ["json", "markdown", "csv", "raw"]


async def _write_raw(
    output_dir: Path,
    requests: list,
    raw_capture_repo: RawCaptureRepository,
) -> list[Path]:
    """Write one file per HTTP exchange under ``output_dir/raw/``.

    For each request we emit ``NNN.request.json`` and ``NNN.response.json``
    so individual exchanges are trivial to diff between captures. SSE
    streams are also expanded into ``NNN.sse.json`` (a list of events)
    when present, since the response body itself is just the raw stream.
    """
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for idx, req in enumerate(requests, start=1):
        if not req.raw_capture_id:
            continue
        capture = await raw_capture_repo.get(req.raw_capture_id)
        if capture is None:
            continue

        cap = capture.model_dump(mode="json")
        prefix = f"{idx:03d}"

        request_doc = {
            "index": idx,
            "request_id": cap.get("id"),
            "session_id": cap.get("session_id"),
            "timestamp": cap.get("timestamp"),
            "provider": cap.get("provider"),
            "method": cap.get("request_method"),
            "url": cap.get("request_url"),
            "headers": cap.get("request_headers", {}),
            "body": cap.get("request_body"),
        }
        request_path = raw_dir / f"{prefix}.request.json"
        request_path.write_text(json.dumps(request_doc, indent=2, default=str), encoding="utf-8")
        written.append(request_path)

        response_doc = {
            "index": idx,
            "request_id": cap.get("id"),
            "status": cap.get("response_status"),
            "headers": cap.get("response_headers", {}),
            "is_streaming": cap.get("is_streaming"),
            "body": cap.get("response_body"),
        }
        response_path = raw_dir / f"{prefix}.response.json"
        response_path.write_text(json.dumps(response_doc, indent=2, default=str), encoding="utf-8")
        written.append(response_path)

        sse_events = cap.get("sse_events") or []
        if sse_events:
            sse_path = raw_dir / f"{prefix}.sse.json"
            sse_path.write_text(json.dumps(sse_events, indent=2, default=str), encoding="utf-8")
            written.append(sse_path)

    return written


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
            path.write_text(content, encoding="utf-8")
            written.append(path)
        elif fmt == "markdown":
            content = render_markdown(session, stats, requests)
            path = output_dir / f"{basename}.md"
            path.write_text(content, encoding="utf-8")
            written.append(path)
        elif fmt == "csv":
            content = render_csv(requests)
            path = output_dir / f"{basename}.csv"
            path.write_text(content, encoding="utf-8")
            written.append(path)
        elif fmt == "raw":
            written.extend(await _write_raw(output_dir, requests, raw_capture_repo))

    return written
