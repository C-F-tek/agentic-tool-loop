#!/usr/bin/env python3
"""Tests for agent_state.py - Generic agent memory and microtask packet helpers."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _get_module():
    """Import agent_state properly using importlib with correct module registration."""
    import importlib.util
    import sys
    
    _memory_dir = Path(__file__).resolve().parent.parent
    _module_name = "agent_state_test"
    _spec = importlib.util.spec_from_file_location(_module_name, _memory_dir / "agent_state.py")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_module_name] = _module
    _spec.loader.exec_module(_module)
    return _module


_m = _get_module()
utc_now_iso = _m.utc_now_iso
sha256_text = _m.sha256_text
clamp_confidence = _m.clamp_confidence
stable_tag_tuple = _m.stable_tag_tuple
json_or_default = _m.json_or_default
compact_text = _m.compact_text
slugify = _m.slugify
keywords = _m.keywords
read_text = _m.read_text
relative_path = _m.relative_path
MemoryRecord = _m.MemoryRecord
load_memory_jsonl = _m.load_memory_jsonl
_connect_db = _m._connect_db
load_memory_db = _m.load_memory_db
build_state_packet = _m.build_state_packet
build_keywords_index = _m.build_keywords_index
select_memory = _m.select_memory
build_memory_index_jsonl = _m.build_memory_index_jsonl
parse_tags = _m.parse_tags
build_memory_delta = _m.build_memory_delta


class TestUtcNowIso:
    """Tests for utc_now_iso."""

    def test_returns_iso_format(self):
        result = utc_now_iso()
        assert isinstance(result, str)
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_returns_utc(self):
        result = utc_now_iso()
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert parsed.tz == timezone.utc


class TestSha256Text:
    """Tests for sha256_text."""

    def test_deterministic(self):
        text = "test content"
        h1 = sha256_text(text)
        h2 = sha256_text(text)
        assert h1 == h2

    def test_returns_hex_string(self):
        result = sha256_text("test")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_different_texts_different_hashes(self):
        h1 = sha256_text("text1")
        h2 = sha256_text("text2")
        assert h1 != h2


class TestClampConfidence:
    """Tests for clamp_confidence."""

    def test_normal_range(self):
        assert clamp_confidence(0.5) == 0.5

    def test_clamp_to_zero(self):
        assert clamp_confidence(-1.0) == 0.0
        assert clamp_confidence(0.0) == 0.0

    def test_clamp_to_one(self):
        assert clamp_confidence(1.0) == 1.0
        assert clamp_confidence(2.0) == 1.0

    def test_string_input(self):
        assert clamp_confidence("0.5") == 0.5


class TestStableTagTuple:
    """Tests for stable_tag_tuple."""

    def test_empty_tags(self):
        assert stable_tag_tuple([]) == ()

    def test_filters_empty_tags(self):
        result = stable_tag_tuple(["valid", "", "   ", "also_valid"])
        assert result == ("valid", "also_valid")

    def test_preserves_order(self):
        result = stable_tag_tuple(["c", "b", "a"])
        assert result == ("c", "b", "a")

    def test_deduplicates(self):
        result = stable_tag_tuple(["a", "b", "a"])
        assert result == ("a", "b")


class TestJsonOrDefault:
    """Tests for json_or_default."""

    def test_valid_json(self):
        result = json_or_default('{"key": "value"}', {})
        assert result == {"key": "value"}

    def test_invalid_json_returns_default(self):
        result = json_or_default("not valid json", "default")
        assert result == "default"

    def test_different_defaults(self):
        assert json_or_default("invalid", None) is None
        assert json_or_default("invalid", []) == []
        assert json_or_default("invalid", 0) == 0


class TestCompactText:
    """Tests for compact_text."""

    def test_collapses_whitespace(self):
        result = compact_text("hello   world    foo")
        assert result == "hello world foo"

    def test_trims_to_limit(self):
        result = compact_text("this is a very long text that should be trimmed", limit=10)
        assert len(result) <= 13

    def test_no_trim_when_short(self):
        result = compact_text("short", limit=100)
        assert result == "short"

    def test_ellipsis_at_limit(self):
        result = compact_text("x" * 100, limit=10)
        assert result.endswith("...")


class TestSlugify:
    """Tests for slugify."""

    def test_simple_string(self):
        assert slugify("Hello World") == "hello_world"

    def test_special_characters(self):
        assert slugify("hello@world#test") == "hello_world_test"

    def test_fallback(self):
        assert slugify("", fallback="default") == "default"

    def test_consecutive_dashes(self):
        assert slugify("hello---world") == "hello_world"


class TestKeywords:
    """Tests for keywords."""

    def test_returns_tuple(self):
        result = keywords("the quick brown fox")
        assert isinstance(result, tuple)

    def test_excludes_stop_words(self):
        result = keywords("the quick brown fox")
        assert "the" not in result

    def test_excludes_digits(self):
        result = keywords("test123 content456")
        assert "123" not in result
        assert "456" not in result

    def test_ranked_by_frequency(self):
        result = keywords("apple apple apple banana banana cherry")
        assert result[0] == "apple"
        assert result[1] == "banana"


class TestReadText:
    """Tests for read_text."""

    def test_reads_file(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")
        result = read_text(file_path)
        assert result == "hello world"

    def test_respects_limit(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("x" * 1000, encoding="utf-8")
        result = read_text(file_path, limit=100)
        assert len(result) <= 100

    def test_handles_encoding_errors(self, tmp_path):
        file_path = tmp_path / "test.bin"
        file_path.write_bytes(b"\xff\xfe")
        result = read_text(file_path)
        assert isinstance(result, str)


class TestRelativePath:
    """Tests for relative_path."""

    def test_relative_to_repo(self, tmp_path):
        repo = tmp_path / "repo"
        file_path = repo / "src" / "file.py"
        repo.mkdir(parents=True)
        file_path.parent.mkdir(parents=True)
        file_path.touch()
        result = relative_path(file_path, repo)
        assert result == Path("src/file.py").as_posix()

    def test_outside_repo_returns_absolute(self, tmp_path):
        file_path = tmp_path / "outside.py"
        file_path.touch()
        repo = tmp_path / "repo"
        repo.mkdir()
        result = relative_path(file_path, repo)
        assert result == str(file_path)


class TestMemoryRecord:
    """Tests for MemoryRecord dataclass."""

    def test_frozen(self):
        record = MemoryRecord(
            record_id="test",
            kind="memory",
            scope="repo",
            source="test",
            summary="test",
            content="test",
        )
        with pytest.raises(Exception):
            record.record_id = "new"

    def test_defaults(self):
        record = MemoryRecord(
            record_id="test",
            kind="memory",
            scope="repo",
            source="test",
            summary="test",
            content="test",
        )
        assert record.tags == ()
        assert record.confidence == 1.0
        assert record.updated_at is None
        assert record.expires_at is None
        assert record.metadata == {}

    def test_from_text(self):
        record = MemoryRecord.from_text(
            kind="task_summary",
            scope="repo",
            source="test.py",
            text="This is a test summary",
            tags=["validated"],
            confidence=0.9,
        )
        assert record.kind == "task_summary"
        assert record.scope == "repo"
        assert record.source == "test.py"
        assert record.confidence == 0.9
        assert "validated" in record.tags
        assert len(record.record_id) == 20

    def test_from_text_truncates_content(self):
        long_text = "x" * 5000
        record = MemoryRecord.from_text(
            kind="memory",
            scope="repo",
            source="test",
            text=long_text,
        )
        assert len(record.content) <= 4200

    def test_from_json(self):
        data = {
            "record_id": "test-id",
            "kind": "validation_result",
            "scope": "repo",
            "source": "test.py",
            "summary": "Test summary",
            "content": "Test content",
            "tags": ["validated", "reviewed"],
            "confidence": 0.85,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        }
        record = MemoryRecord.from_json(json.dumps(data))
        assert record.record_id == "test-id"
        assert record.kind == "validation_result"
        assert record.confidence == 0.85

    def test_from_json_invalid_raises(self):
        with pytest.raises(ValueError):
            MemoryRecord.from_json("not valid")

    def test_from_json_malformed_dict_raises(self):
        with pytest.raises(ValueError):
            MemoryRecord.from_json('"string"')


class TestLoadMemoryJsonl:
    """Tests for load_memory_jsonl."""

    def test_loads_valid_jsonl(self, tmp_path):
        jsonl_path = tmp_path / "memory.jsonl"
        jsonl_path.write_text(
            json.dumps({"record_id": "1", "kind": "memory", "scope": "repo", "source": "s", "summary": "s", "content": "c"}) + "\n",
            encoding="utf-8",
        )
        records = load_memory_jsonl(jsonl_path)
        assert len(records) == 1
        assert records[0].record_id == "1"

    def test_skips_invalid_lines(self, tmp_path):
        jsonl_path = tmp_path / "memory.jsonl"
        jsonl_path.write_text(
            "invalid line\n" + json.dumps({"record_id": "1", "kind": "memory", "scope": "repo", "source": "s", "summary": "s", "content": "c"}) + "\n\n",
            encoding="utf-8",
        )
        records = load_memory_jsonl(jsonl_path)
        assert len(records) == 1

    def test_empty_file(self, tmp_path):
        jsonl_path = tmp_path / "memory.jsonl"
        jsonl_path.touch()
        records = load_memory_jsonl(jsonl_path)
        assert len(records) == 0

    def test_nonexistent_file(self, tmp_path):
        records = load_memory_jsonl(tmp_path / "nonexistent.jsonl")
        assert len(records) == 0


class TestConnectDb:
    """Tests for _connect_db."""

    def test_returns_connection(self, tmp_path):
        db_path = tmp_path / "test.db"
        db_path.touch()
        conn = _connect_db(db_path)
        assert isinstance(conn, sqlite3.Connection)
        conn.close()


class TestLoadMemoryDb:
    """Tests for load_memory_db."""

    def test_creates_schema_and_loads(self, tmp_path):
        db_path = tmp_path / "memory.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE agent_memory (
                record_id TEXT, kind TEXT, scope TEXT, source TEXT,
                summary TEXT, content TEXT, tags TEXT, confidence REAL,
                created_at TEXT, updated_at TEXT, expires_at TEXT, metadata TEXT
            )
        """)
        conn.execute(
            "INSERT INTO agent_memory VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("test-id", "memory", "repo", "src.py", "summary", "content", "[]", 1.0, "2026-01-01", None, None, "{}"),
        )
        conn.commit()
        conn.close()

        records = load_memory_db(db_path)
        assert len(records) == 1
        assert records[0].record_id == "test-id"

    def test_empty_db(self, tmp_path):
        db_path = tmp_path / "memory.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE agent_memory (
                record_id TEXT, kind TEXT, scope TEXT, source TEXT,
                summary TEXT, content TEXT, tags TEXT, confidence REAL,
                created_at TEXT, updated_at TEXT, expires_at TEXT, metadata TEXT
            )
        """)
        conn.commit()
        conn.close()

        records = load_memory_db(db_path)
        assert len(records) == 0

    def test_nonexistent_file(self, tmp_path):
        records = load_memory_db(tmp_path / "nonexistent.db")
        assert len(records) == 0


class TestBuildStatePacket:
    """Tests for build_state_packet."""

    def test_basic_packet(self, tmp_path):
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="content", confidence=0.9),
        ]
        repo_root = tmp_path
        packet = build_state_packet(objective="test", memory_records=records, repo_root=repo_root)

        assert packet["schema_version"] == 1
        assert packet["kind"] == "agent_state_packet"
        assert packet["objective"] == "test"
        assert packet["record_count"] == 1
        assert len(packet["records"]) == 1

    def test_respects_max_chars(self, tmp_path):
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="x" * 1000, confidence=0.9),
        ]
        packet = build_state_packet(objective="test", memory_records=records, repo_root=tmp_path, max_chars=100)
        assert packet["used_chars"] <= 100

    def test_sorts_by_confidence(self, tmp_path):
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="low", confidence=0.3),
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="high", confidence=0.95),
        ]
        packet = build_state_packet(objective="test", memory_records=records, repo_root=tmp_path)
        assert packet["records"][0]["confidence"] > packet["records"][1]["confidence"]


class TestBuildKeywordsIndex:
    """Tests for build_keywords_index."""

    def test_returns_index(self):
        records = [
            MemoryRecord.from_text(kind="task_summary", scope="repo", source="s", text="python testing"),
        ]
        index = build_keywords_index(records)
        assert len(index) == 1
        record_id = list(index.keys())[0]
        assert isinstance(index[record_id], tuple)

    def test_empty_records(self):
        index = build_keywords_index([])
        assert index == {}


class TestSelectMemory:
    """Tests for select_memory."""

    def test_basic_selection(self):
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="python testing"),
        ]
        selected = select_memory(records, objective="python testing")
        assert len(selected) == 1

    def test_kind_filter(self):
        records = [
            MemoryRecord.from_text(kind="task_summary", scope="repo", source="s", text="content"),
            MemoryRecord.from_text(kind="validation_result", scope="repo", source="s", text="content"),
        ]
        selected = select_memory(records, objective="test", kind_filter="task_summary")
        assert len(selected) == 1
        assert selected[0].kind == "task_summary"

    def test_scope_filter(self):
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="content"),
            MemoryRecord.from_text(kind="memory", scope="project", source="s", text="content"),
        ]
        selected = select_memory(records, objective="test", scope_filter="repo")
        assert len(selected) == 1
        assert selected[0].scope == "repo"

    def test_tag_filter(self):
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="content", tags=["validated"]),
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="content", tags=["draft"]),
        ]
        selected = select_memory(records, objective="test", tag_filter="validated")
        assert len(selected) == 1
        assert "validated" in selected[0].tags

    def test_min_confidence(self):
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="high", confidence=0.9),
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="low", confidence=0.3),
        ]
        selected = select_memory(records, objective="test", min_confidence=0.5)
        assert len(selected) == 1
        assert selected[0].confidence >= 0.5

    def test_limit(self):
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text=f"content{i}")
            for i in range(10)
        ]
        selected = select_memory(records, objective="test", limit=3)
        assert len(selected) <= 3

    def test_ranking_by_keywords(self):
        records = [
            MemoryRecord.from_text(kind="task_summary", scope="repo", source="s", text="python testing"),
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="unrelated content"),
        ]
        selected = select_memory(records, objective="python testing")
        assert selected[0].kind == "task_summary"


class TestBuildMemoryIndexJsonl:
    """Tests for build_memory_index_jsonl."""

    def test_writes_jsonl(self, tmp_path):
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="content"),
        ]
        output_path = tmp_path / "index.jsonl"
        build_memory_index_jsonl(records, output_path)
        assert output_path.exists()
        lines = output_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["record_id"] is not None


class TestParseTags:
    """Tests for parse_tags."""

    def test_list(self):
        assert parse_tags(["a", "b"]) == ("a", "b")

    def test_tuple(self):
        assert parse_tags(("a", "b")) == ("a", "b")

    def test_comma_string(self):
        assert parse_tags("a,b,c") == ("a", "b", "c")

    def test_empty(self):
        assert parse_tags("") == ()
        assert parse_tags(None) == ()

    def test_filters_empty(self):
        assert parse_tags(["a", "", "b"]) == ("a", "b")


class TestBuildMemoryDelta:
    """Tests for build_memory_delta."""

    def test_basic_delta(self):
        old_records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="old"),
        ]
        new_records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="new"),
        ]
        delta = build_memory_delta(old_records, new_records)
        assert delta["schema_version"] == 1
        assert delta["kind"] == "memory_delta"
        assert len(delta["added"]) == 1
        assert len(delta["removed"]) == 1
        assert delta["added_count"] == 1
        assert delta["removed_count"] == 1

    def test_unchanged(self):
        record = MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="content")
        delta = build_memory_delta([record], [record])
        assert delta["unchanged_count"] == 1
        assert len(delta["added"]) == 0
        assert len(delta["removed"]) == 0

    def test_empty_sets(self):
        delta = build_memory_delta([], [])
        assert delta["added_count"] == 0
        assert delta["removed_count"] == 0
        assert delta["unchanged_count"] == 0