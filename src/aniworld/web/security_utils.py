"""
Security utilities for AniWorld Downloader
"""

import os
import re
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
        base_allowed_dir: Optional base directory that custom_path must be within
                         (if None, checks against BLOCKED_PATHS instead)
                         
    Returns:
        The validated absolute path string
        
    Raises:
        ValueError: If path is invalid or blocked
    """
    if not custom_path:
        return None
        
    try:
        # Resolve to absolute path to handle ../ traversal
        path_obj = Path(custom_path).resolve()
        path_str = str(path_obj)
        
        # Check against blocked paths (if no specific base allowed dir is enforced)
        if base_allowed_dir is None:
            # Case-insensitive check for Windows paths compatibility
            path_str_lower = path_str.lower()
            
            for blocked in BLOCKED_PATHS:
                # Normalize blocked path
                try:
                    blocked_path = Path(blocked).resolve()
                    
                    # Use commonpath to see if path is inside blocked path
                    if os.path.commonpath([path_obj, blocked_path]) == str(blocked_path):
                         raise ValueError(f"Path is in a blocked system directory: {blocked}")

                except (ValueError, OSError):
                    # Fallback for simple string check if path logic resolution fails
                    if path_str_lower.startswith(str(blocked).lower()):
                         raise ValueError(f"Path is in a blocked system directory (fallback): {blocked}")
                    continue
        else:
            # Enforce base directory restriction (stricter mode)
            base_obj = Path(base_allowed_dir).resolve()
            try:
                # This checks if path_obj is inside base_obj
                path_obj.relative_to(base_obj)
            except ValueError:
                 raise ValueError(f"Path must be within {base_allowed_dir}")
                 
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

def validate_csrf_token(token: str, session_token: str = None) -> bool:
    """
    Validate CSRF token.
    Current implementation requires a token to be present for state-changing requests if auth is enabled.
    """
    # If no token provided, failed
    if not token:
        return False
        
    # TODO: Implement strict per-session CSRF token verification (HMAC)
    # For now, we enforce that a token exists and matches a basic pattern
    # Real implementations should compare this against a value stored in the user's session
    
    if len(token) < 32:
        return False
        
    return True
