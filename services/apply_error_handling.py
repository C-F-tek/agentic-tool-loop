# ------------------------------------------------------------------
# Apply Error Handling Framework to All Broker Scripts
# ------------------------------------------------------------------
# This script applies the error handling framework to all existing
# broker scripts.
# ------------------------------------------------------------------

import os
import sys
from pathlib import Path

# Add the services directory to path
sys.path.insert(0, "services")

from aicarmine_broker.error_handling import ErrorHandlingApplier

def main():
    """Apply error handling to all broker scripts."""
    # Create applier for the broker directory
    applier = ErrorHandlingApplier("services/aicarmine_broker")
    
    # Find all Python files
    files = applier.find_all_python_files()
    print(f"Found {len(files)} Python files")
    
    # Check which files need error handling
    needs_handling = [f for f in files if applier.needs_error_handling(f)]
    print(f"Files needing error handling: {len(needs_handling)}")
    
    # Apply to all files
    results = applier.apply_to_all()
    print(f"Applied to: {len(results['applied_files'])} files")
    print(f"Skipped: {len(results['skipped_files'])} files")
    print(f"Errors: {len(results['errors'])}")
    
    # List applied files
    if results["applied_files"]:
        print("\nApplied files:")
        for f in results["applied_files"][:10]:
            print(f"  - {f}")
        if len(results["applied_files"]) > 10:
            print(f"  ... and {len(results['applied_files']) - 10} more")

if __name__ == "__main__":
    main()