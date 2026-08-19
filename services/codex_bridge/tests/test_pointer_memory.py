"""Tests for pointer memory modules: PointerGraph, PointerNode, ResumeContext, RevisionPointer."""

import sys
from pathlib import Path
import unittest

# Add the codex_bridge directory to sys.path
_test_dir = Path(__file__).parent
_codex_bridge_dir = _test_dir.parent
sys.path.insert(0, str(_codex_bridge_dir))

from pointer_memory import (
    PointerGraph,
    PointerNode,
    ResumeContext,
    RevisionPointer,
    get_previous_block_id,
    get_next_block_id,
    get_refines_block_id,
    get_resume_from_block_id,
    has_previous,
    has_next,
    has_refines,
    resume_anchor,
    can_resume_forward,
    build_resume_context,
    build_revision_pointer,
    extract_pointer_fields,
    build_pointer_contract,
)


class TestPointerNode(unittest.TestCase):
    def test_pointer_node_defaults(self):
        node = PointerNode()
        self.assertEqual(node.block_id, "")
        self.assertEqual(node.previous_block_id, "")
        self.assertEqual(node.next_block_id, "")
        self.assertEqual(node.refines_block_id, "")
        self.assertEqual(node.resume_from_block_id, "")

    def test_pointer_node_get_methods(self):
        node = PointerNode(
            block_id="block_1",
            previous_block_id="prev_block",
            next_block_id="next_block",
            refines_block_id="refine_block",
            resume_from_block_id="resume_block",
        )
        self.assertEqual(node.get_previous(), "prev_block")
        self.assertEqual(node.get_next(), "next_block")
        self.assertEqual(node.get_refines(), "refine_block")
        self.assertEqual(node.get_resume_from(), "resume_block")


class TestPointerGraph(unittest.TestCase):
    def test_pointer_graph_add_and_get_node(self):
        graph = PointerGraph()
        node1 = PointerNode(block_id="block_1")
        node2 = PointerNode(block_id="block_2", previous_block_id="block_1")
        graph.add_node(node1)
        graph.add_node(node2)
        
        self.assertEqual(graph.latest_block_id, "block_2")
        self.assertEqual(graph.get_node("block_1"), node1)
        self.assertEqual(graph.get_node("block_2"), node2)

    def test_pointer_graph_has_previous(self):
        graph = PointerGraph()
        node1 = PointerNode(block_id="block_1")
        node2 = PointerNode(block_id="block_2", previous_block_id="block_1")
        graph.add_node(node1)
        graph.add_node(node2)
        
        self.assertTrue(graph.has_previous("block_2"))
        self.assertFalse(graph.has_previous("block_1"))

    def test_pointer_graph_has_next(self):
        graph = PointerGraph()
        node1 = PointerNode(block_id="block_1", next_block_id="block_2")
        node2 = PointerNode(block_id="block_2")
        graph.add_node(node1)
        graph.add_node(node2)
        
        self.assertTrue(graph.has_next("block_1"))
        self.assertFalse(graph.has_next("block_2"))

    def test_pointer_graph_has_refines(self):
        graph = PointerGraph()
        node1 = PointerNode(block_id="block_1", refines_block_id="refine_block")
        node2 = PointerNode(block_id="refine_block")
        graph.add_node(node1)
        graph.add_node(node2)
        
        self.assertTrue(graph.has_refines("block_1"))


class TestResumeContext(unittest.TestCase):
    def test_resume_context_defaults(self):
        context = ResumeContext()
        self.assertEqual(context.resume_from_block_id, "")
        self.assertEqual(context.latest_block_id, "")
        self.assertFalse(context.continuation_required)

    def test_resume_context_can_resume_forward(self):
        context1 = ResumeContext(resume_from_block_id="resume_block")
        self.assertTrue(context1.can_resume_forward())
        
        context2 = ResumeContext()
        self.assertFalse(context2.can_resume_forward())


class TestRevisionPointer(unittest.TestCase):
    def test_revision_pointer_defaults(self):
        pointer = RevisionPointer()
        self.assertEqual(pointer.block_id, "")
        self.assertFalse(pointer.has_backward_pointer())
        self.assertFalse(pointer.has_forward_pointer())

    def test_revision_pointer_has_pointers(self):
        pointer = RevisionPointer(
            previous_block_id="prev_block",
            refines_block_id="refine_block",
            next_block_id="next_block",
            resume_from_block_id="resume_block",
        )
        self.assertTrue(pointer.has_backward_pointer())
        self.assertTrue(pointer.has_forward_pointer())


class TestPointerFunctions(unittest.TestCase):
    def test_get_previous_block_id(self):
        node = PointerNode(previous_block_id="prev_block")
        self.assertEqual(get_previous_block_id(node), "prev_block")
        
        dict_node = {"previous_block_id": "dict_prev"}
        self.assertEqual(get_previous_block_id(dict_node), "dict_prev")

    def test_get_next_block_id(self):
        node = PointerNode(next_block_id="next_block")
        self.assertEqual(get_next_block_id(node), "next_block")
        
        dict_node = {"next_block_id": "dict_next"}
        self.assertEqual(get_next_block_id(dict_node), "dict_next")

    def test_get_refines_block_id(self):
        node = PointerNode(refines_block_id="refine_block")
        self.assertEqual(get_refines_block_id(node), "refine_block")
        
        dict_node = {"refines_block_id": "dict_refine"}
        self.assertEqual(get_refines_block_id(dict_node), "dict_refine")

    def test_get_resume_from_block_id(self):
        node = PointerNode(resume_from_block_id="resume_block")
        self.assertEqual(get_resume_from_block_id(node), "resume_block")
        
        dict_node = {"resume_from_block_id": "dict_resume"}
        self.assertEqual(get_resume_from_block_id(dict_node), "dict_resume")

    def test_build_resume_context(self):
        revision_context = {
            "resume_from_block_id": "resume_block",
            "latest_block_id": "latest_block",
            "proposal_block_id": "proposal_block",
        }
        context = build_resume_context(revision_context)
        self.assertEqual(context.resume_from_block_id, "resume_block")
        self.assertEqual(context.latest_block_id, "latest_block")
        self.assertEqual(context.proposal_block_id, "proposal_block")

    def test_build_revision_pointer(self):
        revision_context = {
            "block_id": "block_1",
            "previous_block_id": "prev_block",
            "next_block_id": "next_block",
            "refines_block_id": "refine_block",
            "resume_from_block_id": "resume_block",
        }
        pointer = build_revision_pointer(revision_context)
        self.assertEqual(pointer.block_id, "block_1")
        self.assertEqual(pointer.previous_block_id, "prev_block")
        self.assertEqual(pointer.next_block_id, "next_block")
        self.assertEqual(pointer.refines_block_id, "refine_block")
        self.assertEqual(pointer.resume_from_block_id, "resume_block")

    def test_extract_pointer_fields(self):
        revision_context = {
            "previous_block_id": "prev",
            "next_block_id": "next",
            "refines_block_id": "refine",
            "resume_from_block_id": "resume",
            "proposal_block_id": "proposal",
            "latest_block_id": "latest",
        }
        fields = extract_pointer_fields(revision_context)
        self.assertEqual(fields["previous_block_id"], "prev")
        self.assertEqual(fields["next_block_id"], "next")
        self.assertEqual(fields["refines_block_id"], "refine")
        self.assertEqual(fields["resume_from_block_id"], "resume")
        self.assertEqual(fields["proposal_block_id"], "proposal")
        self.assertEqual(fields["latest_block_id"], "latest")

    def test_build_pointer_contract(self):
        pointer = RevisionPointer(
            resume_from_block_id="resume_block",
            latest_block_id="latest_block",
            proposal_block_id="proposal_block",
            previous_block_id="prev_block",
            refines_block_id="refine_block",
        )
        contract = build_pointer_contract(pointer)
        self.assertTrue(contract["product_contract"])
        self.assertTrue(contract["decision_recovery"])
        self.assertTrue(contract["closure_owner"])
        self.assertTrue(contract["primary_closer"])


if __name__ == "__main__":
    unittest.main()