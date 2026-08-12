"""
Script to detect and remove invisible Unicode characters (watermarks) from source files.
"""
import os
import re
import sys

# Invisible Unicode characters to remove
INVISIBLE_CHARS = re.compile(
    r'[\u200B-\u200D\u200E-\u200F\uFEFF\u2060\u2800\u1800\u2028\u2029\u202A-\u202E]'
)

def scan_file(filepath):
    """Scan a file for invisible Unicode characters."""
    try:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            content = f.read()
        matches = INVISIBLE_CHARS.findall(content)
        return len(matches), matches
    except Exception as e:
        return 0, []

def clean_file(filepath):
    """Remove invisible Unicode characters from a file."""
    try:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        cleaned = INVISIBLE_CHARS.sub('', content)
        
        if cleaned != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(cleaned)
            return True
        return False
    except Exception as e:
        print(f"Error cleaning {filepath}: {e}")
        return False

def main():
    """Main function to scan and clean files."""
    target_files = [
        'audit_mcp_allowlist.py',
        'same-capability-serious-scan.json',
        'codex_ollama_bridge_applied/aicarmine-executor-server.py',
        'services/aicarmine-executor-server.py',
        'services/aicarmine_codex_mcp_server.py',
        'services/aicarmine_broker/job_html.py',
    ]
    
    print("=" * 60)
    print("INVISIBLE WATERMARK DETECTION AND CLEANING")
    print("=" * 60)
    
    cleaned_count = 0
    for filepath in target_files:
        count, matches = scan_file(filepath)
        if count > 0:
            print(f"\nFOUND {count} invisible character(s) in: {filepath}")
            print(f"  Characters found: {repr(''.join(matches[:20]))}")
            if clean_file(filepath):
                print(f"  -> CLEANED successfully")
                cleaned_count += 1
            else:
                print(f"  -> CLEAN FAILED")
        else:
            print(f"CLEAN: {filepath}")
    
    print(f"\n{'=' * 60}")
    print(f"CLEANED {cleaned_count}/{len(target_files)} files")
    print(f"{'=' * 60}\n")

if __name__ == '__main__':
    main()