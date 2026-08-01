"""Fix all remaining corrupted indentation and syntax patterns in aicarmine_broker/."""
import re
import os

base = r'aicarmine_broker'
count = 0
for root, dirs, files in os.walk(base):
    for f in files:
        if not f.endswith('.py'):
            continue
        path = os.path.join(root, f)
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                content = fh.read()
            original = content
            
            # Fix: except Exception:\n                return (16 spaces)
            content = re.sub(r'except Exception:\s*\n\s{16}return', 'except Exception as exc:\n        return', content)
            
            # Fix: except Exception:\n                pass\n        return
            content = re.sub(r'except Exception:\s*\n\s{16}pass\s*\n\s{8}return', 'except Exception as exc:\n        return', content)
            
            # Fix: except Exception:\n            return (12 spaces)
            content = re.sub(r'except Exception:\s*\n\s{12}return', 'except Exception as exc:\n        return', content)
            
            # Fix: except Exception as exec: or exe
            content = re.sub(r'except Exception as (exec|exe):', 'except Exception as exc:', content)
            
            # Fix: except Exception:\n                return (with different return content)
            content = re.sub(r'except Exception:\s*\n\s{16}return\s+[\w\.\(\)\"\']+', 'except Exception as exc:\n        return', content)
            
            # Fix: unterminated f-string in raise BrokerError
            content = re.sub(
                r'raise BrokerError\(\s*\n\s{12}message=f"Error in \{__name__\}:\s*\n\s{12}error_type',
                'raise BrokerError(\n            message=f"Error in {__name__}: {exc}",\n            error_type',
                content
            )
            
            # Fix: unindent does not match any outer indentation level (45 spaces)
            content = re.sub(r'\}\s*\n\s{45}return', '}\n        return', content)
            
            if content != original:
                with open(path, 'w', encoding='utf-8') as fh:
                    fh.write(content)
                count += 1
                print(f'Fixed: {path}')
        except Exception as e:
            print(f'Error: {path}: {e}')

print(f'Done. Fixed {count} files.')