
import sys
import os
import pathlib
import logging

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

try:
    from aniworld.web.security_utils import validate_custom_path
    from aniworld import config
except ImportError:
    # Try importing assuming we are in src directory
    try:
        sys.path.append(os.path.dirname(os.getcwd()))
        from aniworld.web.security_utils import validate_custom_path
        from aniworld import config
    except ImportError as e:
        print(f"Error importing modules: {e}")
        print("Please run this script from the src directory.")
        sys.exit(1)

def test_path_validation():
    print("Running Path Traversal Verification...")
    
    default_base = config.DEFAULT_ALLOWED_DOWNLOAD_BASE
    print(f"Default Base: {default_base}")
    
    # Ensure default download path exists for testing
    download_dir = pathlib.Path(config.DEFAULT_DOWNLOAD_PATH)
    if not download_dir.exists():
        try:
            download_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Warning: Could not create default download directory: {e}")

    test_cases = [
        {
            "name": "Valid Path in Defaults",
            "path": str(download_dir / "Anime"),
            "base": default_base,
            "should_pass": True
        },
        {
            "name": "Simple Traversal Attempt",
            "path": str(download_dir / "../Outside"),
            "base": default_base,
            "should_pass": False
        },
        {
            "name": "Root Traversal Attempt",
            "path": "C:/Windows",
            "base": default_base,
            "should_pass": False
        },
        ( # Explicitly using C:/Windows which is in BLOCKED_PATHS
            "Blocked Path Direct",
            "C:\\Windows\\System32",
            None, # Even without base, it should be blocked by blocklist
            False
        ),
        (
            "Valid Subdirectory Creation",
            str(download_dir / "New Folder" / "Deep"),
            default_base,
            True
        )
    ]

    failed = 0
    
    for case in test_cases:
        if isinstance(case, tuple):
             name, path, base, should_pass = case
        else:
             name = case["name"]
             path = case["path"]
             base = case["base"]
             should_pass = case["should_pass"]

        print(f"\nTest: {name}")
        print(f"  Input: {path}")
        print(f"  Base: {base}")
        
        try:
            result = validate_custom_path(path, base_allowed_dir=base)
            if should_pass:
                print(f"  [PASS] Passed (Allowed as expected): {result}")
            else:
                print(f"  [FAIL] Failed (Allowed but should be blocked): {result}")
                failed += 1
        except ValueError as e:
            if should_pass:
                print(f"  [FAIL] Failed (Blocked but should be allowed): {e}")
                failed += 1
            else:
                print(f"  [PASS] Passed (Blocked as expected): {e}")

    print("\n" + "="*30)
    if failed == 0:
        print("ALL PATH TRAVERSAL CHECKS PASSED [PASS]")
    else:
        print(f"{failed} TESTS FAILED [FAIL]")

if __name__ == "__main__":
    test_path_validation()
