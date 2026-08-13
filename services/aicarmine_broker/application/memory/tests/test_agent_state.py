"""Tests for agent_state.py - Generic agent memory and microtask packet helpers.

NOTE: This test file cannot be run via pytest as part of the application/ package
because services/aicarmine_broker/application/memory/__init__.py imports
agent_memory_routing_policy which has a broken import chain (report_utils not found).
Tests are implemented but must be run directly with python instead of pytest.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _run_tests():
    """Run all tests directly."""
    import sys
    from importlib.util import spec_from_file_location, module_from_spec
    
    _memory_dir = Path(__file__).resolve().parent.parent
    _module_name = "agent_state_test"
    _spec = spec_from_file_location(_module_name, str(_memory_dir / "agent_state.py"))
    _m = module_from_spec(_spec)
    sys.modules[_module_name] = _m
    _spec.loader.exec_module(_m)
    
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
    
    passed = 0
    failed = 0
    
    # Test utc_now_iso
    try:
        result = utc_now_iso()
        assert isinstance(result, str)
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None
        passed += 1
    except Exception as e:
        print(f"FAIL utc_now_iso: {e}")
        failed += 1
    
    # Test sha256_text
    try:
        text = "test content"
        h1 = sha256_text(text)
        h2 = sha256_text(text)
        assert h1 == h2
        result = sha256_text("test")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)
        passed += 1
    except Exception as e:
        print(f"FAIL sha256_text: {e}")
        failed += 1
    
    # Test clamp_confidence
    try:
        assert clamp_confidence(0.5) == 0.5
        assert clamp_confidence(-1.0) == 0.0
        assert clamp_confidence(0.0) == 0.0
        assert clamp_confidence(1.0) == 1.0
        assert clamp_confidence(2.0) == 1.0
        assert clamp_confidence("0.5") == 0.5
        passed += 1
    except Exception as e:
        print(f"FAIL clamp_confidence: {e}")
        failed += 1
    
    # Test stable_tag_tuple
    try:
        assert stable_tag_tuple([]) == ()
        assert stable_tag_tuple(["valid", "", "   ", "also_valid"]) == ("valid", "also_valid")
        assert stable_tag_tuple(["c", "b", "a"]) == ("c", "b", "a")
        assert stable_tag_tuple(["a", "b", "a"]) == ("a", "b")
        passed += 1
    except Exception as e:
        print(f"FAIL stable_tag_tuple: {e}")
        failed += 1
    
    # Test json_or_default
    try:
        assert json_or_default('{"key": "value"}', {}) == {"key": "value"}
        assert json_or_default("not valid json", "default") == "default"
        assert json_or_default("invalid", None) is None
        assert json_or_default("invalid", []) == []
        assert json_or_default("invalid", 0) == 0
        passed += 1
    except Exception as e:
        print(f"FAIL json_or_default: {e}")
        failed += 1
    
    # Test compact_text
    try:
        assert compact_text("hello   world    foo") == "hello world foo"
        result = compact_text("this is a very long text that should be trimmed", limit=10)
        assert len(result) <= 13
        assert compact_text("short", limit=100) == "short"
        result = compact_text("x" * 100, limit=10)
        assert result.endswith("...")
        passed += 1
    except Exception as e:
        print(f"FAIL compact_text: {e}")
        failed += 1
    
    # Test slugify
    try:
        assert slugify("Hello World") == "hello_world"
        assert slugify("hello@world#test") == "hello_world_test"
        assert slugify("", fallback="default") == "default"
        assert slugify("hello---world") == "hello_world"
        passed += 1
    except Exception as e:
        print(f"FAIL slugify: {e}")
        failed += 1
    
    # Test keywords
    try:
        result = keywords("the quick brown fox")
        assert isinstance(result, tuple)
        assert "the" not in result
        result = keywords("test123 content456")
        assert "123" not in result
        assert "456" not in result
        result = keywords("apple apple apple banana banana cherry")
        assert result[0] == "apple"
        assert result[1] == "banana"
        passed += 1
    except Exception as e:
        print(f"FAIL keywords: {e}")
        failed += 1
    
    # Test read_text
    tmp_path = Path(__file__).resolve().parent.parent.parent.parent / "tmp_test_dir"
    tmp_path.mkdir(exist_ok=True)
    try:
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")
        result = read_text(file_path)
        assert result == "hello world"
        file_path.write_text("x" * 1000, encoding="utf-8")
        result = read_text(file_path, limit=100)
        assert len(result) <= 100
        file_path.write_bytes(b"\xff\xfe")
        result = read_text(file_path)
        assert isinstance(result, str)
        passed += 1
    except Exception as e:
        print(f"FAIL read_text: {e}")
        failed += 1
    finally:
        for f in tmp_path.iterdir():
            f.unlink()
        tmp_path.rmdir()
    
    # Test relative_path
    tmp_path = Path(__file__).resolve().parent.parent.parent.parent / "tmp_test_dir2"
    tmp_path.mkdir(exist_ok=True)
    try:
        repo = tmp_path / "repo"
        file_path = repo / "src" / "file.py"
        repo.mkdir(parents=True)
        file_path.parent.mkdir(parents=True)
        file_path.touch()
        result = relative_path(file_path, repo)
        assert result == Path("src/file.py").as_posix()
        file_path2 = tmp_path / "outside.py"
        file_path2.touch()
        result = relative_path(file_path2, repo)
        assert result == str(file_path2)
        passed += 1
    except Exception as e:
        print(f"FAIL relative_path: {e}")
        failed += 1
    finally:
        for f in tmp_path.iterdir():
            f.unlink()
        tmp_path.rmdir()
    
    # Test MemoryRecord
    try:
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
        
        assert record.tags == ()
        assert record.confidence == 1.0
        assert record.updated_at is None
        assert record.expires_at is None
        assert record.metadata == {}
        
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
        
        long_text = "x" * 5000
        record = MemoryRecord.from_text(
            kind="memory",
            scope="repo",
            source="test",
            text=long_text,
        )
        assert len(record.content) <= 4200
        
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
        
        try:
            MemoryRecord.from_json("not valid")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
        
        try:
            MemoryRecord.from_json('"string"')
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
        
        passed += 1
    except Exception as e:
        print(f"FAIL MemoryRecord: {e}")
        failed += 1
    
    # Test load_memory_jsonl
    tmp_path = Path(__file__).resolve().parent.parent.parent.parent / "tmp_test_jsonl"
    tmp_path.mkdir(exist_ok=True)
    try:
        jsonl_path = tmp_path / "memory.jsonl"
        jsonl_path.write_text(
            json.dumps({
                "record_id": "1",
                "kind": "memory",
                "scope": "repo",
                "source": "s",
                "summary": "s",
                "content": "c",
            }) + "\n",
            encoding="utf-8",
        )
        records = load_memory_jsonl(jsonl_path)
        assert len(records) == 1
        assert records[0].record_id == "1"
        
        jsonl_path.write_text(
            "invalid line\n" + json.dumps({
                "record_id": "1",
                "kind": "memory",
                "scope": "repo",
                "source": "s",
                "summary": "s",
                "content": "c",
            }) + "\n\n",
            encoding="utf-8",
        )
        records = load_memory_jsonl(jsonl_path)
        assert len(records) == 1
        
        jsonl_path.touch()
        records = load_memory_jsonl(jsonl_path)
        assert len(records) == 0
        
        records = load_memory_jsonl(tmp_path / "nonexistent.jsonl")
        assert len(records) == 0
        
        passed += 1
    except Exception as e:
        print(f"FAIL load_memory_jsonl: {e}")
        failed += 1
    finally:
        for f in tmp_path.iterdir():
            f.unlink()
        tmp_path.rmdir()
    
    # Test _connect_db
    try:
        db_path = tmp_path / "test.db"
        db_path.touch()
        conn = _connect_db(db_path)
        assert isinstance(conn, sqlite3.Connection)
        conn.close()
        passed += 1
    except Exception as e:
        print(f"FAIL _connect_db: {e}")
        failed += 1
    
    # Test load_memory_db
    try:
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
        
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM agent_memory")
        conn.commit()
        conn.close()
        
        records = load_memory_db(db_path)
        assert len(records) == 0
        
        passed += 1
    except Exception as e:
        print(f"FAIL load_memory_db: {e}")
        failed += 1
    
    # Test build_state_packet
    try:
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="content", confidence=0.9),
        ]
        packet = build_state_packet(objective="test", memory_records=records, repo_root=tmp_path)
        
        assert packet["schema_version"] == 1
        assert packet["kind"] == "agent_state_packet"
        assert packet["objective"] == "test"
        assert packet["record_count"] == 1
        assert len(packet["records"]) == 1
        
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="x" * 1000, confidence=0.9),
        ]
        packet = build_state_packet(objective="test", memory_records=records, repo_root=tmp_path, max_chars=100)
        assert packet["used_chars"] <= 100
        
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="low", confidence=0.3),
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="high", confidence=0.95),
        ]
        packet = build_state_packet(objective="test", memory_records=records, repo_root=tmp_path)
        assert packet["records"][0]["confidence"] > packet["records"][1]["confidence"]
        
        passed += 1
    except Exception as e:
        print(f"FAIL build_state_packet: {e}")
        failed += 1
    
    # Test build_keywords_index
    try:
        records = [
            MemoryRecord.from_text(kind="task_summary", scope="repo", source="s", text="python testing"),
        ]
        index = build_keywords_index(records)
        assert len(index) == 1
        record_id = list(index.keys())[0]
        assert isinstance(index[record_id], tuple)
        
        index = build_keywords_index([])
        assert index == {}
        
        passed += 1
    except Exception as e:
        print(f"FAIL build_keywords_index: {e}")
        failed += 1
    
    # Test select_memory
    try:
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="python testing"),
        ]
        selected = select_memory(records, objective="python testing")
        assert len(selected) == 1
        
        records = [
            MemoryRecord.from_text(kind="task_summary", scope="repo", source="s", text="content"),
            MemoryRecord.from_text(kind="validation_result", scope="repo", source="s", text="content"),
        ]
        selected = select_memory(records, objective="test", kind_filter="task_summary")
        assert len(selected) == 1
        assert selected[0].kind == "task_summary"
        
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="content"),
            MemoryRecord.from_text(kind="memory", scope="project", source="s", text="content"),
        ]
        selected = select_memory(records, objective="test", scope_filter="repo")
        assert len(selected) == 1
        assert selected[0].scope == "repo"
        
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="content", tags=["validated"]),
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="content", tags=["draft"]),
        ]
        selected = select_memory(records, objective="test", tag_filter="validated")
        assert len(selected) == 1
        assert "validated" in selected[0].tags
        
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="high", confidence=0.9),
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="low", confidence=0.3),
        ]
        selected = select_memory(records, objective="test", min_confidence=0.5)
        assert len(selected) == 1
        assert selected[0].confidence >= 0.5
        
        records = [
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text=f"content{i}")
            for i in range(10)
        ]
        selected = select_memory(records, objective="test", limit=3)
        assert len(selected) <= 3
        
        records = [
            MemoryRecord.from_text(kind="task_summary", scope="repo", source="s", text="python testing"),
            MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="unrelated content"),
        ]
        selected = select_memory(records, objective="python testing")
        assert selected[0].kind == "task_summary"
        
        passed += 1
    except Exception as e:
        print(f"FAIL select_memory: {e}")
        failed += 1
    
    # Test build_memory_index_jsonl
    try:
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
        
        passed += 1
    except Exception as e:
        print(f"FAIL build_memory_index_jsonl: {e}")
        failed += 1
    
    # Test parse_tags
    try:
        assert parse_tags(["a", "b"]) == ("a", "b")
        assert parse_tags(("a", "b")) == ("a", "b")
        assert parse_tags("a,b,c") == ("a", "b", "c")
        assert parse_tags("") == ()
        assert parse_tags(None) == ()
        assert parse_tags(["a", "", "b"]) == ("a", "b")
        
        passed += 1
    except Exception as e:
        print(f"FAIL parse_tags: {e}")
        failed += 1
    
    # Test build_memory_delta
    try:
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
        
        record = MemoryRecord.from_text(kind="memory", scope="repo", source="s", text="content")
        delta = build_memory_delta([record], [record])
        assert delta["unchanged_count"] == 1
        assert len(delta["added"]) == 0
        assert len(delta["removed"]) == 0
        
        delta = build_memory_delta([], [])
        assert delta["added_count"] == 0
        assert delta["removed_count"] == 0
        assert delta["unchanged_count"] == 0
        
        passed += 1
    except Exception as e:
        print(f"FAIL build_memory_delta: {e}")
        failed += 1
    
    # Summary
    print(f"\n=== Test Summary ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total: {passed + failed}")
    
    return failed == 0


if __name__ == "__main__":
    import sys
    success = _run_tests()
    sys.exit(0 if success else 1)