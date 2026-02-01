import unittest
import os
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from aniworld.web.security_utils import validate_custom_path, sanitize_url, SYSTEM_USER_ID, BLOCKED_PATHS

class TestSecurityUtils(unittest.TestCase):
    def test_sanitize_url(self):
        # Valid URLs
        self.assertEqual(sanitize_url("https://example.com"), "https://example.com")
        self.assertEqual(sanitize_url("http://example.com/image.png"), "http://example.com/image.png")
        
        # Malicious URLs
        self.assertEqual(sanitize_url("javascript:alert(1)"), "")
        self.assertEqual(sanitize_url("data:text/html,script"), "")
        self.assertEqual(sanitize_url("vbscript:msgbox"), "")
        
        # Injection attempts
        self.assertEqual(sanitize_url('https://example.com" onmouseover="alert(1)'), 'https://example.com%22 onmouseover=%22alert(1)')
        self.assertEqual(sanitize_url("https://example.com'"), "https://example.com%27")

    def test_validate_custom_path_blocked(self):
        # Blocked paths
        blocked = []
        
        if os.name == 'nt':
            blocked.append("C:\\Windows\\System32")
            blocked.append("C:\\ProgramData\\AniWorld")
            blocked.append("C:\\Program Files\\Test")
        else:
            blocked.append("/etc/passwd")
            blocked.append("/var/log/syslog")
            blocked.append("/root/secret")
            
        # Docker path should be blocked if we consider it an absolute path
        # On Windows C:\app\data would be blocked if /app/data resolves to it
        # But /app/data usually resolves to drive root.
        
        for path in blocked:
            try:
                validate_custom_path(path)
                self.fail(f"Path {path} should be blocked but was allowed")
            except ValueError:
                pass

    def test_validate_custom_path_allowed(self):
        # Allowed paths (relative to current or safe)
        # Note: validate_custom_path resolves paths.
        # We need a path that is NOT in BLOCKED_PATHS.
        # Temp dir or current dir should be safe?
        
        cwd = os.getcwd()
        # Ensure CWD is not blocked (it shouldn't be usually, but lets be sure)
        # If running in /app/data it might fail? No, user is on Windows User home.
        
        try:
            val = validate_custom_path("test_download_folder")
            self.assertTrue(str(val).endswith("test_download_folder"))
        except ValueError as e:
            self.fail(f"Valid path raised ValueError: {e}")

if __name__ == '__main__':
    unittest.main()
