"""Tests for agent memory models: MemoryRecord, AgentMicroTask."""

import sys
from pathlib import Path
import unittest

# Add the codex_bridge directory to sys.path
_test_dir = Path(__file__).parent
_codex_bridge_dir = _test_dir.parent
sys.path.insert(0, str(_codex_bridge_dir))

from agent_memory_models import (
    MemoryRecord,
    AgentMicroTask,
    build_state_packet,
)


class TestMemoryRecord(unittest.TestCase):
    def test_memory_record_from_text(self):
        record = MemoryRecord.from_text(
            kind="test_kind",
            scope="project",
            source="test_source",
            text="This is a test memory record content.",
            tags=["tag1", "tag2"],
            confidence=0.95,
        )
        self.assertEqual(record.kind, "test_kind")
        self.assertEqual(record.scope, "project")
        self.assertEqual(record.source, "test_source")
        self.assertEqual(record.confidence, 0.95)
        self.assertIn("This is a test memory record content.", record.summary)

    def test_memory_record_to_dict(self):
        record = MemoryRecord(
            record_id="rec_123",
            kind="test_kind",
            scope="project",
            source="test_source",
            summary="Test summary",
            content="Test content",
            tags=("tag1", "tag2"),
            confidence=0.9,
        )
        data = record.to_dict()
        self.assertEqual(data["record_id"], "rec_123")
        self.assertEqual(data["kind"], "test_kind")
        self.assertEqual(data["scope"], "project")
        self.assertEqual(data["source"], "test_source")
        self.assertEqual(data["summary"], "Test summary")
        self.assertEqual(data["content"], "Test content")
        self.assertEqual(data["tags"], ["tag1", "tag2"])


class TestAgentMicroTask(unittest.TestCase):
    def test_agent_micro_task_defaults(self):
        task = AgentMicroTask(
            task_id="task_1",
            title="Test Task",
            lane="test_lane",
            purpose="Test purpose",
        )
        self.assertEqual(task.task_id, "task_1")
        self.assertEqual(task.title, "Test Task")
        self.assertEqual(task.lane, "test_lane")
        self.assertEqual(task.purpose, "Test purpose")
        self.assertEqual(task.priority, 5)
        self.assertFalse(task.blocking)
        self.assertEqual(task.status, "planned")

    def test_agent_micro_task_to_dict(self):
        task = AgentMicroTask(
            task_id="task_1",
            title="Test Task",
            lane="test_lane",
            purpose="Test purpose",
            priority=7,
            blocking=True,
            status="running",
            inputs=("input1", "input2"),
            expected_outputs=("output1",),
            depends_on=("dep_task_1",),
        )
        data = task.to_dict()
        self.assertEqual(data["task_id"], "task_1")
        self.assertEqual(data["priority"], 7)
        self.assertTrue(data["blocking"])
        self.assertEqual(data["status"], "running")
        self.assertEqual(data["inputs"], ["input1", "input2"])
        self.assertEqual(data["expected_outputs"], ["output1"])
        self.assertEqual(data["depends_on"], ["dep_task_1"])


class TestStatePacket(unittest.TestCase):
    def test_build_state_packet(self):
        records = [
            MemoryRecord.from_text(
                kind="memory",
                scope="project",
                source="source1",
                text="Content 1",
                confidence=0.9,
            ),
            MemoryRecord.from_text(
                kind="memory",
                scope="project",
                source="source2",
                text="Content 2",
                confidence=0.8,
            ),
        ]
        packet = build_state_packet(records, objective="Test objective", query="test query")
        self.assertEqual(packet["objective"], "Test objective")
        self.assertEqual(packet["query"], "test query")
        self.assertEqual(packet["records_count"], 2)
        self.assertIn("packet_content", packet)


if __name__ == "__main__":
    unittest.main()