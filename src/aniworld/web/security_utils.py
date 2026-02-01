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
                    blocked_str = str(blocked_path)
                    
                    if str(path_obj) == blocked_str or str(path_obj).startswith(str(blocked_path) + os.sep):
                        raise ValueError(f"Path is in a blocked system directory: {blocked}")
                        
                    # Also check simple string matching for cases where resolve() might be tricky 
                    # (e.g. non-existent paths on different OS)
                    if path_str_lower.startswith(str(blocked).lower()):
                         raise ValueError(f"Path is in a blocked system directory: {blocked}")
                         
                except ValueError as ve:
                    raise ve
                except Exception:
                    # Ignore resolution errors for paths not on this OS
                    continue
        else:
            # Enforce base directory restriction (stricter mode)
            base_obj = Path(base_allowed_dir).resolve()
            if not str(path_obj).startswith(str(base_obj)):
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
    """
    if not url:
        return ""
        
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return ""
            
        # Basic sanitization of special characters that could be used for injection
        # Current major browsers encode these anyway, but good for safety
        clean_url = url.replace('"', '%22').replace("'", '%27').replace('<', '%3C').replace('>', '%3E')
        
        return clean_url
    except Exception:
        return ""

def validate_csrf_token(token: str) -> bool:
    """
    Validate CSRF token (placeholder for future implementation)
    """
    return True
