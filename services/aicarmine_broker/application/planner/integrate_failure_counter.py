"""Auto-integrate failure_counter into loop.py

This script patches services/aicarmine_broker/application/planner/loop.py
to add failure_counter.increment() calls at key decision rejection points.

Run: python integrate_failure_counter.py
"""

import sys
from pathlib import Path

LOOP_PY = Path(__file__).parent / "loop.py"

# ─── Step 1: Verify failure_counter import is present ─────────────────
with open(LOOP_PY, "r") as f:
    content = f.read()

if "_get_failure_counter" not in content:
    print("✗ _get_failure_counter import NOT found in loop.py")
    print("  Run: Add 'from ...application.job.failure_counter import get_counter as _get_failure_counter' after line 27")
    sys.exit(1)
else:
    print("✓ failure_counter already imported in loop.py")

# ─── Step 2: Find and patch rejection points ──────────────────────────
# We need to add failure tracking after each append_agent_event("planner_decision_rejected", ...)
# followed by the "row = {" block.

# Define the insertion pattern: after "append_agent_event("planner_decision_rejected", ..."
# and before "row = {" we insert failure counter tracking.

FAILURE_TRACKING_BLOCK = '''
                # Track failure counts for planner decision patterns
                failure_counter = _get_failure_counter()
                if job_id:
                    guard_type = guard_result.get("guard_type", "")
                    if guard_type:
                        failure_counter.increment(job_id, guard_type)
'''

# Count how many rejection points exist
import re
rejected_events = re.findall(r'append_agent_event\(\s*job_id,\s*"planner_decision_rejected"', content)
print(f"  Found {len(rejected_events)} planner_decision_rejected events")

# ─── Step 3: Apply patches ────────────────────────────────────────────
# Strategy: Find each "row = {" block that follows append_agent_event("planner_decision_rejected", ...)
# and insert failure tracking before it.

lines = content.split("\n")
new_lines = []
insertion_count = 0
in_rejection_block = False
brace_depth = 0

i = 0
while i < len(lines):
    line = lines[i]
    
    # Detect the start of a rejection event
    if 'append_agent_event(' in line and '"planner_decision_rejected"' in line:
        in_rejection_block = True
        new_lines.append(line)
        i += 1
        continue
    
    # If we're in a rejection block, look for "row = {"
    if in_rejection_block and 'row = {' in line and 'step' in line:
        # Insert failure tracking before row = {
        indent = "                "
        tracking_lines = FAILURE_TRACKING_BLOCK.strip().split("\n")
        for tl in tracking_lines:
            new_lines.append(indent + tl)
        insertion_count += 1
        in_rejection_block = False
    
    new_lines.append(line)
    i += 1

# ─── Step 4: Write changes ────────────────────────────────────────────
content = "\n".join(new_lines)
with open(LOOP_PY, "w") as f:
    f.write(content)

print(f"✓ Added {insertion_count} failure_counter.increment() calls to loop.py")
print("")
print("Done! The following has been applied:")
print("  1. _get_failure_counter import (line 28)")
print(f"  2. {insertion_count} failure tracking blocks inserted before rejection rows")
print("")
print("To verify, search for 'failure_counter.increment' in loop.py")