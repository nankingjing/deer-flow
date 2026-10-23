"""Markdown write path for the opt-in ``MarkdownMemoryStorage`` backend."""

import json
from pathlib import Path

import pytest

from deerflow.agents.memory.backends.deermem.deermem.config import DeerMemConfig
from deerflow.agents.memory.backends.deermem.deermem.core import markdown_format as mf
from deerflow.agents.memory.backends.deermem.deermem.core import storage as storage_module
from deerflow.agents.memory.backends.deermem.deermem.core.markdown_storage import MarkdownMemoryStorage
from deerflow.agents.memory.backends.deermem.deermem.core.storage import (
    FileMemoryStorage,
    MemoryManifestRevisionConflict,
    create_empty_memory,
)


def _markdown_storage(root: Path) -> MarkdownMemoryStorage:
    return MarkdownMemoryStorage(DeerMemConfig(storage_path=str(root), retrieval_adapter=""))


def test_save_writes_markdown_and_round_trips_through_both_readers(tmp_path):
    """The write path renders Markdown; JSON and Markdown reads agree exactly."""
    storage = _markdown_storage(tmp_path)
    coded = "用户偏好：先给结论。\n```python\nprint('hi')\n```"
    memory = create_empty_memory()
    memory["user"]["workContext"]["summary"] = coded
    memory["user"]["topOfMind"]["summary"] = "keep the ``` fence"
    memory["history"]["recentMonths"]["summary"] = "café ☕"

    assert storage.save(memory) is True

    memory_file = tmp_path / "memory.json"
    raw = memory_file.read_text(encoding="utf-8")
    assert raw.startswith("# DeerFlow Memory")
    assert "```memory-json" in raw

    manifest = storage._load_memory_file(memory_file)
    assert manifest is not None
    assert manifest["user"]["workContext"]["summary"] == coded
    assert mf._parse_markdown_memory(raw) == manifest

    # The same reader must also accept the JSON encoding of that exact manifest.
    json_twin = tmp_path / "memory-json-twin.json"
    json_twin.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    assert storage._load_memory_file(json_twin) == manifest

    loaded = storage.reload()
    assert loaded["user"]["workContext"]["summary"] == coded
    assert loaded["history"]["recentMonths"]["summary"] == "café ☕"
    assert not list(tmp_path.glob("memory.json.corrupt-*"))


def test_expected_revision_mismatch_does_not_clobber_markdown_summary(tmp_path):
    storage = _markdown_storage(tmp_path)
    memory = create_empty_memory()
    memory["user"]["workContext"]["summary"] = "original"
    assert storage.save(memory) is True
    memory_file = tmp_path / "memory.json"
    before = memory_file.read_bytes()

    replacement = create_empty_memory()
    replacement["user"]["workContext"]["summary"] = "stale writer"
    with pytest.raises(MemoryManifestRevisionConflict):
        storage.save(replacement, expected_revision=0)

    assert memory_file.read_bytes() == before
    assert storage.reload()["user"]["workContext"]["summary"] == "original"


def test_corrupt_summary_is_quarantined_and_rebuilt_as_markdown(tmp_path):
    memory_file = tmp_path / "memory.json"
    corrupt = b'{"version": "2.0", "revision": 41, "user": {"work'
    memory_file.write_bytes(corrupt)
    storage = _markdown_storage(tmp_path)

    assert storage.save(create_empty_memory()) is True

    quarantined = list(tmp_path.glob("memory.json.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == corrupt
    rebuilt = memory_file.read_text(encoding="utf-8")
    assert rebuilt.startswith("# DeerFlow Memory")
    assert "```memory-json" in rebuilt
    assert storage.reload()["revision"] == 1


def test_default_json_backend_keeps_the_exact_json_bytes(tmp_path, monkeypatch):
    """The default storage class still publishes the unchanged JSON document."""
    monkeypatch.setattr(storage_module, "utc_now_iso_z", lambda: "2026-01-02T03:04:05Z")
    memory = create_empty_memory()
    memory["user"]["workContext"]["summary"] = "stable"
    storage = FileMemoryStorage(DeerMemConfig(storage_path=str(tmp_path), retrieval_adapter=""))

    assert storage.save(memory) is True

    expected = {
        "version": "2.0",
        "revision": 1,
        "lastUpdated": "2026-01-02T03:04:05Z",
        "user": memory["user"],
        "history": memory["history"],
    }
    raw = (tmp_path / "memory.json").read_bytes()
    assert raw == json.dumps(expected, ensure_ascii=False, indent=2).encode("utf-8")
    assert b"```memory-json" not in raw
