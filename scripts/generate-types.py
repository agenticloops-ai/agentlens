#!/usr/bin/env python3
"""Generate TypeScript types from Pydantic models.

Imports all Pydantic models from agentlens.models, builds a combined
JSON Schema with every model in ``$defs``, then converts the whole thing to
TypeScript interfaces via ``json-schema-to-typescript`` (npx).

The result is written to ``web/src/types/generated.ts``.

Usage:
    python scripts/generate-types.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Models to generate types for (import order matters for readability)
# ---------------------------------------------------------------------------

from agentlens.models import (
    ImageContent,
    LLMRequest,
    Message,
    RawCapture,
    Session,
    SessionStats,
    TextContent,
    ThinkingContent,
    TokenUsage,
    ToolDefinition,
    ToolResultContent,
    ToolUseContent,
)

MODELS = [
    TextContent,
    ImageContent,
    ThinkingContent,
    ToolUseContent,
    ToolResultContent,
    Message,
    ToolDefinition,
    TokenUsage,
    LLMRequest,
    Session,
    SessionStats,
    RawCapture,
]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"
OUTPUT_FILE = WEB_DIR / "src" / "types" / "generated.ts"

HEADER = "// Auto-generated from Pydantic models \u2014 do not edit manually\n"


def _build_combined_schema() -> dict:
    """Build a single JSON Schema that references every model via ``$defs``.

    Each model gets its own key under ``$defs``.  The top-level schema uses
    ``anyOf`` to reference all of them so that ``json-schema-to-typescript``
    emits an interface for every definition.
    """
    defs: dict = {}
    refs: list[dict] = []

    for model in MODELS:
        schema = model.model_json_schema()
        name = model.__name__

        # If the model schema itself has $defs (for nested models), merge them
        # into the top-level $defs and rewrite local $ref pointers.
        local_defs = schema.pop("$defs", {})
        for def_name, def_schema in local_defs.items():
            # Only add if not already present (first definition wins)
            if def_name not in defs:
                defs[def_name] = def_schema

        defs[name] = schema
        refs.append({"$ref": f"#/$defs/{name}"})

    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "anyOf": refs,
        "$defs": defs,
    }


def _clean_output(raw_ts: str) -> str:
    """Post-process the ``json-schema-to-typescript`` output.

    - Strip the per-file boilerplate comment it adds.
    - Remove the top-level unnamed union type (the ``anyOf`` wrapper).
    """
    # Remove the auto-generated header comment block
    cleaned = re.sub(
        r"/\*\s*eslint-disable\s*\*/\s*"
        r"/\*\*\s*\n"
        r"\s*\*\s*This file was automatically generated.*?\*/\s*\n?",
        "",
        raw_ts,
        flags=re.DOTALL,
    )
    return cleaned.strip()


def main() -> None:
    tmp_dir = Path(tempfile.mkdtemp(prefix="agentlens-schemas-"))

    try:
        # 1. Build a single combined schema
        combined = _build_combined_schema()
        schema_path = tmp_dir / "combined.json"
        schema_path.write_text(json.dumps(combined, indent=2))

        # Also dump individual schemas for reference / debugging
        for model in MODELS:
            individual = model.model_json_schema()
            (tmp_dir / f"{model.__name__}.json").write_text(
                json.dumps(individual, indent=2)
            )

        # 2. Convert the combined schema to TypeScript
        result = subprocess.run(
            [
                "npx",
                "--yes",
                "json-schema-to-typescript",
                "--additionalProperties=false",
                str(schema_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(WEB_DIR),
        )

        if result.returncode != 0:
            print(
                f"ERROR running json-schema-to-typescript:\n{result.stderr}",
                file=sys.stderr,
            )
            sys.exit(1)

        ts_output = _clean_output(result.stdout)

        # 3. Write the final file
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_FILE.open("w") as fh:
            fh.write(HEADER)
            fh.write("\n")
            fh.write(ts_output)
            fh.write("\n")

        print(f"Generated {OUTPUT_FILE.relative_to(PROJECT_ROOT)}")

    finally:
        # 4. Clean up
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
