import os, glob

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
    
    # Fix pattern: except Exception as _e:\n        raise BrokerError(\n            except Exception as exc:\n        raise BrokerError(
    # This is the broken duplicate pattern from the fix script
    old_pattern = '''except Exception as _e:
        raise BrokerError(
            except Exception as exc:
        raise BrokerError(
            message=f"Error in {__name__}: error_type={type(exc).__name__}, error_message={str(exc)}",
            error_type=type(exc).__name__,
            error_message=str(exc),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )'''
    new_pattern = '''except Exception:
        raise BrokerError(
            message=f"Error in {__name__}: error_type=Exception, error_message=unhandled",
            error_type="Exception",
            error_message="unhandled",
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )'''
    if old_pattern in content:
        content = content.replace(old_pattern, new_pattern)
        count += 1
    
    # Fix pattern: except Exception as _e:\n        raise BrokerError(\n            ...message=f"Error in {__name__}...
    # Replace with simple except Exception: pass or raise
    old_pattern2 = '''except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}: error_type=type(_e).__name__, error_message=str(_e)",
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )'''
    new_pattern2 = '''except Exception:
        raise BrokerError(
            message=f"Error in {__name__}: error_type=Exception, error_message=unhandled",
            error_type="Exception",
            error_message="unhandled",
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )'''
    if old_pattern2 in content:
        content = content.replace(old_pattern2, new_pattern2)
        count += 1
        
    # Fix pattern: except Exception as _e:\n        raise BrokerError(\n            message=f"Error in {__name__}: error_type=type(exc).__name__...
    old_pattern3 = '''except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}: error_type=type(exc).__name__, error_message=str(exc)",
            error_type=type(exc).__name__,
            error_message=str(exc),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )'''
    new_pattern3 = '''except Exception:
        raise BrokerError(
            message=f"Error in {__name__}: error_type=Exception, error_message=unhandled",
            error_type="Exception",
            error_message="unhandled",
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )'''
    if old_pattern3 in content:
        content = content.replace(old_pattern3, new_pattern3)
        count += 1

    # Fix pattern: except Exception as _e:\n        raise BrokerError(\n            message=f"Error in {__name__}: error_type=type(_e).__name__...
    old_pattern4 = '''except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}: error_type=type(_e).__name__, error_message=str(_e)",
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )'''
    new_pattern4 = '''except Exception:
        raise BrokerError(
            message=f"Error in {__name__}: error_type=Exception, error_message=unhandled",
            error_type="Exception",
            error_message="unhandled",
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )'''
    if old_pattern4 in content:
        content = content.replace(old_pattern4, new_pattern4)
        count += 1

    if content != original:
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write(content)
        fixed_files.append(f)

print(f'Done. Fixed {count} patterns in {len(fixed_files)} files.')
for ff in fixed_files:
    print(f'  - {ff}')