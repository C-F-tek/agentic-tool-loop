"""Fix all corrupted indentation patterns from regex fix script."""
import os, re, glob

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
    
    # Fix pattern: except Exception:\n                pass\n        return f"<unstringifiable:...
    pattern = re.compile(
        r'except Exception:\s*\n\s{12,}pass\s*\n\s{8}return f"<unstringifiable:\{type\(exc\)\.__name__\}>"',
    )
    matches = list(pattern.finditer(content))
    if matches:
        for match in reversed(matches):
            replacement = 'except Exception:\n        return f"<unstringifiable:Exception>"'
            content = content[:match.start()] + replacement + content[match.end():]
        count += len(matches)
        fixed_files.append(f)
    
    # Fix pattern: except Exception:\n                pass\n        logger.
    pattern2 = re.compile(
        r'except Exception:\s*\n\s{12,}pass\s*\n\s{8}logger\.',
    )
    matches = list(pattern2.finditer(content))
    if matches:
        for match in reversed(matches):
            start = match.start()
            pass_end = content.find('\n', start) + 1
            content = content[:start] + content[pass_end:]
        count += len(matches)
        fixed_files.append(f)
    
    # Fix pattern: except Exception:\n                pass\n        raise
    pattern3 = re.compile(
        r'except Exception:\s*\n\s{12,}pass\s*\n\s{8}raise',
    )
    matches = list(pattern3.finditer(content))
    if matches:
        for match in reversed(matches):
            start = match.start()
            pass_end = content.find('\n', start) + 1
            content = content[:start] + content[pass_end:]
        count += len(matches)
        fixed_files.append(f)
    
    if content != original:
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write(content)

print(f'Done. Fixed {count} patterns in {len(fixed_files)} files.')
for ff in fixed_files:
    print(f'  - {ff}')