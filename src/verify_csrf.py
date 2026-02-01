
import sys
import os
import unittest
import secrets

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

try:
    from aniworld.web.security_utils import generate_csrf_token, validate_csrf_token
except ImportError:
    try:
        sys.path.append(os.path.dirname(os.getcwd()))
        from aniworld.web.security_utils import generate_csrf_token, validate_csrf_token
    except ImportError as e:
        print(f"Error importing modules: {e}")
        sys.exit(1)

class TestCSRF(unittest.TestCase):
    def test_generate_token(self):
        token = generate_csrf_token()
        self.assertIsInstance(token, str)
        self.assertEqual(len(token), 64) # 32 bytes hex = 64 chars
        
        token2 = generate_csrf_token()
        self.assertNotEqual(token, token2)

    def test_validate_token(self):
        token = generate_csrf_token()
        
        # Valid case: token matches session token (simulating Double Submit pattern where session_token IS the cookie value)
        # Note: In our implementation, we compare the header token against the cookie token.
        # Ideally, validate_csrf_token(header_token, cookie_token) should return True if they match.
        
        self.assertTrue(validate_csrf_token(token, token))
        
        # Invalid case: mismatch
        self.assertFalse(validate_csrf_token(token, "wrong_token"))
        
        # Invalid case: empty
        self.assertFalse(validate_csrf_token(token, ""))
        self.assertFalse(validate_csrf_token("", token))
        self.assertFalse(validate_csrf_token(None, token))

if __name__ == "__main__":
    print("Running CSRF Verification...")
    unittest.main()
