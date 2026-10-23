"""Markdown-aware parsing for DeerMem user-memory summaries.

This module is intentionally dependency-free so it can be unit-tested and
imported without the rest of the DeerMem stack.

Design
------
A Markdown summary carries its *lossless* state inside a fenced
```` ```memory-json ```` block. When loading, the fenced JSON block is the
only trusted Markdown representation: if it is present and parses to a JSON
object it is returned verbatim; anything else (no fence, malformed fence,
non-object JSON) yields ``None`` so the caller can decide policy (the
default is to quarantine the unreadable file rather than silently rebuild
over persistent state).

:func:`_render_markdown_memory` writes that representation: the fenced block
holds the exact manifest as pretty-printed JSON, and the human-readable notes
below it are derived from the same payload and never parsed back. The fence is
emitted first so remembered text that itself contains a ```` ```memory-json ````
fence cannot divert the reader's fence search.

The JSON decoder locates the end of the value before the closing fence is
checked. Backticks inside remembered strings cannot truncate the value, and
later fenced notes cannot be accidentally consumed as part of the JSON.

A lossy structured parse of the human-readable sections is deliberately NOT
provided: it cannot reproduce the manifest schema (``user``/``history`` must
be objects, ``version``/``revision`` scalars) and previously surfaced as
``ValueError``/``AttributeError`` crashes on the very hand-edited files the
loader claimed to tolerate.
"""

from __future__ import annotations

import json
import re
from typing import Any

_OPEN_FENCE_RE = re.compile(r"```memory-json[ \t]*\r?\n")
_CLOSE_FENCE_RE = re.compile(r"[ \t\r\n]*\r?\n[ \t]*```[ \t]*(?:\r?\n|$)")


def _parse_markdown_memory(raw: str) -> dict[str, Any] | None:
    """Parse a Markdown summary into a dict, or None when nothing usable.

    Only the fenced ```` ```memory-json ```` block is trusted. There is no
    structured fallback: without a valid fenced block the file cannot be
    mapped onto the manifest schema losslessly, so returning ``None`` (the
    caller quarantines and starts fresh) is the honest outcome.
    """
    opening = _OPEN_FENCE_RE.search(raw)
    if opening is None:
        return None
    payload = raw[opening.end() :].lstrip()
    try:
        value, end = json.JSONDecoder().raw_decode(payload)
    except json.JSONDecodeError:
        return None
    if _CLOSE_FENCE_RE.match(payload, end) is None:
        return None
    return value if isinstance(value, dict) else None


def _render_markdown_memory(memory_file: dict[str, Any]) -> str:
    """Render a summary manifest as Markdown with a lossless fenced block.

    The fenced block carries the manifest verbatim, so :func:`_parse_markdown_memory`
    reads back an identical dict. Notes are presentation only: values are
    JSON-encoded onto one line so embedded newlines and code fences cannot
    break the surrounding document.
    """
    lines = [
        "# DeerFlow Memory",
        "",
        "<!-- Lossless state lives in the fenced block; the notes below are derived. -->",
        "```memory-json",
        json.dumps(memory_file, ensure_ascii=False, indent=2),
        "```",
    ]
    for section in ("user", "history"):
        values = memory_file.get(section)
        if not isinstance(values, dict) or not values:
            continue
        lines.extend(["", f"## {section.capitalize()}"])
        for key, value in values.items():
            lines.append(f"- **{key}**: {json.dumps(value, ensure_ascii=False)}")
    lines.append("")
    return "\n".join(lines)
