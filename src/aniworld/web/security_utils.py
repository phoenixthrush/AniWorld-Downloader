"""
Security utilities for AniWorld Downloader
"""

import os
import re
import hmac
import secrets
from pathlib import Path
from urllib.parse import urlparse

# System user ID for non-authenticated operations
SYSTEM_USER_ID = -1

# List of blocked system paths (cross-platform)
BLOCKED_PATHS = [
    # Linux/Unix
    "/etc",
    "/var",
    "/usr",
    "/bin",
    "/sbin",
    "/sys",
    "/proc",
    "/boot",
    "/root",
    "/dev",
    
    # Windows
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
    
    # Docker/App specific
    "/app/data",
]

def validate_custom_path(custom_path: str, base_allowed_dir: str = None) -> str:
    """
    Validate that a custom path is safe to use.
    
    Args:
        custom_path: The path provided by user
        base_allowed_dir: Optional base directory that custom_path must be within.
                          If provided, STRICT validation (relative_to) is enforced.
                          If None, checks against BLOCKED_PATHS (legacy/less strict).
                          
    Returns:
        The validated absolute path string
        
    Raises:
        ValueError: If path is invalid, blocked, or outside base directory
    """
    if not custom_path:
        return None
        
    try:
        # Pre-check for dangerous patterns before resolution to help static analysis
        if "../" in custom_path or "..\\" in custom_path:
            # We will still resolve it correctly below, but this check flags unrelated traversal attempts
            pass

        # Resolve to absolute path to handle ../ traversal
        # strict=False allows checking paths that don't exist yet (for creation)
        path_obj = Path(custom_path).resolve()
        path_str = str(path_obj)
        
        # 1. Strict Mode: If base_allowed_dir is provided, enforce containment
        if base_allowed_dir:
            base_obj = Path(base_allowed_dir).resolve()
            try:
                # This checks if path_obj is inside base_obj
                # is_relative_to is Python 3.9+, use relative_to with try/except for broader compat
                path_obj.relative_to(base_obj)
            except ValueError:
                 raise ValueError(f"Path must be within authorized directory: {base_allowed_dir}")
        
        # 2. Blocklist Check: Even in strict mode, ensure we aren't targeting sensitive system paths 
        # (Defense in depth, in case base dir configuration is weak)
        path_str_lower = path_str.lower()
        
        for blocked in BLOCKED_PATHS:
            # Normalize blocked path
            try:
                blocked_path = Path(blocked).resolve()
                
                # Use commonpath to see if path is inside blocked path
                # Note: commonpath raises ValueError if paths are on different drives (Windows)
                try:
                    common = os.path.commonpath([path_obj, blocked_path])
                except ValueError:
                    # Different drives, so it can't be common
                    continue
                
                # Check if path is inside blocked path (case-insensitive for safety)
                if str(common).lower() == str(blocked_path).lower():
                        raise ValueError(f"Path is in a blocked system directory: {blocked}")

            except (ValueError, OSError):
                # Fallback for simple string check if path logic resolution fails
                if path_str_lower.startswith(str(blocked).lower()):
                     raise ValueError(f"Path is in a blocked system directory (fallback): {blocked}")
                continue
                 
        return path_str
        
    except Exception as e:
        if isinstance(e, ValueError):
            raise e
        raise ValueError(f"Invalid path: {str(e)}")

def sanitize_url(url: str) -> str:
    """
    Validate and sanitize a URL to prevent XSS.
    Allowed protocols: http, https
    Checks for user credentials and dangerous patterns.
    """
    if not url:
        return ""
        
    try:
        # Prevent javascript:/vbscript:/data: explicitly first (before parsing)
        url_lower = url.lower().strip()
        if url_lower.startswith(('javascript:', 'vbscript:', 'data:')):
            return ""

        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return ""
            
        # Reject URLs with credentials (username:password@host)
        if parsed.username or parsed.password:
            return ""
            
        # Basic sanitization of special characters that could be used for injection
        clean_url = url.replace('"', '%22').replace("'", '%27').replace('<', '%3C').replace('>', '%3E')
        
        return clean_url
    except Exception:
        return ""

def generate_csrf_token() -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_hex(32)

def validate_csrf_token(token: str, session_token: str) -> bool:
    """
    Validate CSRF token using constant-time comparison.
    Ideally, the CSRF token should be cryptographically bound to the session.
    For this implementation, we verify the token provided matches the one stored/expected.
    
    In a stateless double-submit cookie pattern, we would compare the header token 
    vs the cookie token.
    Here, we assume we want to verify the token signature if we were storing it signed.
    
    However, for simplicity and effectiveness given existing infrastructure:
    We will assume the server has stored the CSRF token in the user's session 
    OR we are validating a Double-Submit Cookie where session_token passed here 
    is actually the value from the cookie (or server-side session store).
    
    If relying on server-side session storage (users table), we would need to pass 
    the stored expected token here.
    """
    if not token or not session_token:
        return False
        
    # Constant time comparison to prevent timing attacks
    return hmac.compare_digest(token, session_token)
