"""
Full repository scan to detect and remove invisible Unicode characters (watermarks).
"""
import os
import re

# Invisible Unicode characters to remove
INVISIBLE_CHARS = re.compile(
    r'[\u200B-\u200D\u200E-\u200F\uFEFF\u2060\u2800\u1800\u2028\u2029\u202A-\u202E]'
)

# Extensions to scan
TARGET_EXTENSIONS = ('.py', '.md', '.json', '.yaml', '.yml', '.txt', '.html', '.css', '.js', '.ts')

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
    """Main function to scan and clean entire repository."""
    print("=" * 60)
    print("FULL REPOSITORY INVISIBLE WATERMARK SCAN AND CLEAN")
    print("=" * 60)
    
    found_files = []
    cleaned_count = 0
    
    for root, dirs, files in os.walk('.'):
        # Skip .git and node_modules and .venv for cleaner output
        skip_dirs = ['.git', 'node_modules', '.venv', '$null', 'diag-qwen30b-20260607-133905']
        if any(d in root.split(os.sep) for d in skip_dirs):
            continue
            
        for f in files:
            if f.endswith(TARGET_EXTENSIONS):
                filepath = os.path.join(root, f)
                count, matches = scan_file(filepath)
                if count > 0:
                    found_files.append((filepath, count, matches))
                    if clean_file(filepath):
                        cleaned_count += 1
    
    # Report results
    if found_files:
        print(f"\nFOUND {sum(c for _, c, _ in found_files)} invisible character(s) across {len(found_files)} files:\n")
        for filepath, count, matches in found_files:
            print(f"  {filepath}: {count} char(s) -> {repr(''.join(matches[:20]))}")
        
        print(f"\n{'=' * 60}")
        print(f"CLEANED {cleaned_count}/{len(found_files)} files")
        print(f"{'=' * 60}\n")
    else:
        print("\nNO INVISIBLE WATERMARKS FOUND - ALL CLEAR\n")
        print(f"{'=' * 60}\n")

if __name__ == '__main__':
    main()