"""Comprehensive fix for all broken except Exception: patterns without body."""
import os, glob, re

os.chdir('C:/Users/sanit/agentic-tool-loop/services')
files = glob.glob('aicarmine_broker/**/*.py', recursive=True)
count = 0
fixed_files = []

for f in files:
    if not os.path.isfile(f) or not f.endswith('.py'):
        continue
    with open(f, 'r', encoding='utf-8') as fh:
        content = fh.read()
    original = content
    
    # Pattern 1: except Exception:\n        raise BrokerError(...)
    # Replace the broken pattern with a simple pass
    pattern1 = re.compile(
        r'except Exception:\s*\n\s+raise BrokerError\(\s*\n\s+message=f"Error in \{__name__\}:.*?\n\s+error_type=.*?\n\s+error_message=.*?\n\s+category=ErrorCategory\.RUNTIME,\s*\n\s+severity=ErrorSeverity\.HIGH,\s*\n\s+\)',
        re.DOTALL
    )
    matches = list(pattern1.finditer(content))
    if matches:
        for match in reversed(matches):
            replacement = 'except Exception:\n                pass'
            content = content[:match.start()] + replacement + content[match.end():]
        count += len(matches)
        fixed_files.append(f)
    
    # Pattern 2: except Exception:\n        raise BrokerError(\n            message=f"Error in {__name__}: error_type=Exception, error_message=unhandled",\n            error_type="Exception",\n            error_message="unhandled",\n            category=ErrorCategory.RUNTIME,\n            severity=ErrorSeverity.HIGH,\n        )
    pattern2 = re.compile(
        r'except Exception:\s*\n\s+raise BrokerError\(\s*\n\s+message=f"Error in \{__name__\}: error_type=Exception, error_message=unhandled",\s*\n\s+error_type="Exception",\s*\n\s+error_message="unhandled",\s*\n\s+category=ErrorCategory\.RUNTIME,\s*\n\s+severity=ErrorSeverity\.HIGH,\s*\n\s+\)',
        re.DOTALL
    )
    matches = list(pattern2.finditer(content))
    if matches:
        for match in reversed(matches):
            replacement = 'except Exception:\n                pass'
            content = content[:match.start()] + replacement + content[match.end():]
        count += len(matches)
        if f not in fixed_files:
            fixed_files.append(f)
    
    if content != original:
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write(content)

print(f'Done. Fixed {count} patterns in {len(fixed_files)} files.')
for ff in fixed_files:
    print(f'  - {ff}')