#!/usr/bin/env python
"""Find deps dict and config dict locations in planner.py"""

import re

with open('services/aicarmine_broker/planner.py', 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.split('\n')

# Find the return statement
for i, line in enumerate(lines):
    if 'return _run_agentic_planner_job_impl(' in line:
        print(f"Found at line {i+1}:")
        # Print next 130 lines
        for j in range(i, min(i+130, len(lines))):
            print(f"{j+1}: {lines[j]}")
        break