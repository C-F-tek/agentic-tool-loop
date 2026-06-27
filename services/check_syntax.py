import ast
import sys

path = r'services/aicarmine_broker/application/planner/loop.py'
with open(path) as f:
    src = f.read()

try:
    ast.parse(src)
    print('SYNTAX_OK')
except SyntaxError as e:
    print(f'SYNTAX_ERROR: {e}')
    sys.exit(1)