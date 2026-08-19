"""Tests for chunk management modules: CodeChunk, EvidenceChunk, ProposalChunk."""

import sys
from pathlib import Path
import unittest

# Add the codex_bridge directory to sys.path
_test_dir = Path(__file__).parent
_codex_bridge_dir = _test_dir.parent
sys.path.insert(0, str(_codex_bridge_dir))

from chunk_management import (
    CodeChunk,
    EvidenceChunk,
    ProposalChunk,
    build_code_chunk_sequence,
    concat_code_chunks,
    build_evidence_chunk_sequence,
    concat_evidence_chunks,
    build_proposal_chunk_sequence,
    concat_proposal_chunks,
)


class TestCodeChunk(unittest.TestCase):
    def test_code_chunk_defaults(self):
        chunk = CodeChunk()
        self.assertEqual(chunk.chunk_id, "")
        self.assertEqual(chunk.path, "")
        self.assertEqual(chunk.symbol, "")
        self.assertEqual(chunk.kind, "semantic_code_chunk")

    def test_code_chunk_can_concat_with(self):
        chunk1 = CodeChunk(path="test.py", line_start=1, line_end=10)
        chunk2 = CodeChunk(path="test.py", line_start=11, line_end=20)
        self.assertTrue(chunk1.can_concat_with(chunk2))

        chunk3 = CodeChunk(path="other.py", line_start=1, line_end=10)
        self.assertFalse(chunk1.can_concat_with(chunk3))


class TestEvidenceChunk(unittest.TestCase):
    def test_evidence_chunk_defaults(self):
        chunk = EvidenceChunk()
        self.assertEqual(chunk.chunk_id, "")
        self.assertEqual(chunk.name, "")
        self.assertEqual(chunk.requirement, "")

    def test_evidence_chunk_can_concat_with(self):
        chunk1 = EvidenceChunk(requirement="test_req", name="test_name")
        chunk2 = EvidenceChunk(requirement="test_req", name="test_name_2")
        self.assertTrue(chunk1.can_concat_with(chunk2))


class TestProposalChunk(unittest.TestCase):
    def test_proposal_chunk_defaults(self):
        chunk = ProposalChunk()
        self.assertEqual(chunk.chunk_id, "")
        self.assertEqual(chunk.name, "")
        self.assertEqual(chunk.kind, "proposal_chunk")

    def test_proposal_chunk_can_concat_with(self):
        chunk1 = ProposalChunk(proposal_block_id="block_1")
        chunk2 = ProposalChunk(proposal_block_id="block_1")
        self.assertTrue(chunk1.can_concat_with(chunk2))

        chunk3 = ProposalChunk(proposal_block_id="block_2")
        self.assertFalse(chunk1.can_concat_with(chunk3))


class TestChunkSequences(unittest.TestCase):
    def test_build_code_chunk_sequence(self):
        chunks_data = [
            {"chunk_id": "c1", "path": "test.py", "line_start": 1, "line_end": 10},
            {"chunk_id": "c2", "path": "test.py", "line_start": 11, "line_end": 20},
        ]
        sequence = build_code_chunk_sequence(chunks_data)
        self.assertEqual(len(sequence), 2)
        self.assertEqual(sequence[0].chunk_id, "c1")
        self.assertEqual(sequence[1].chunk_id, "c2")

    def test_build_evidence_chunk_sequence(self):
        chunks_data = [
            {"name": "e1", "requirement": "req1"},
            {"name": "e2", "requirement": "req2"},
        ]
        sequence = build_evidence_chunk_sequence(chunks_data)
        self.assertEqual(len(sequence), 2)

    def test_build_proposal_chunk_sequence(self):
        chunks_data = [
            {"chunk_id": "p1", "name": "prop1", "proposal_block_id": "block_1"},
            {"chunk_id": "p2", "name": "prop2", "proposal_block_id": "block_1"},
        ]
        sequence = build_proposal_chunk_sequence(chunks_data)
        self.assertEqual(len(sequence), 2)


class TestChunkConcatenation(unittest.TestCase):
    def test_concat_code_chunks(self):
        chunks = [
            CodeChunk(path="test.py", content_preview="line1\nline2"),
            CodeChunk(path="other.py", content_preview="line3\nline4"),
        ]
        result = concat_code_chunks(chunks)
        self.assertIn("## test.py", result)
        self.assertIn("## other.py", result)

    def test_concat_evidence_chunks(self):
        chunks = [
            EvidenceChunk(requirement="req1", name="e1", effective_passed=True),
            EvidenceChunk(requirement="req2", name="e2", effective_passed=False, degraded=True),
        ]
        result = concat_evidence_chunks(chunks)
        self.assertIn("Total evidence chunks:", result)

    def test_concat_proposal_chunks(self):
        chunks = [
            ProposalChunk(name="prop1", proposal_block_id="block_1", quality_passed=True, exit_decision="PATCHABLE_TARGET"),
            ProposalChunk(name="prop2", proposal_block_id="block_2", quality_passed=False, exit_decision="BLOCKED"),
        ]
        result = concat_proposal_chunks(chunks)
        self.assertIn("## Proposal:", result)


if __name__ == "__main__":
    unittest.main()