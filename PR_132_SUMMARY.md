# PR #132 Review Summary

Hi @Domekologe! 👋

Thank you for your contribution! The features you've added (download cancellation, auto-sync, and custom paths) are really useful and well-implemented from a functionality perspective. However, I've identified several security issues that need to be addressed before this can be merged.

## 🔴 Critical Issues (Must Fix)

### 1. Path Traversal Vulnerability
**Problem:** The `custom_path` parameter isn't validated, allowing users to download to any directory on the system (e.g., `/etc/`, `/tmp/`).

**Fix needed in `app.py`:**
```python
from pathlib import Path

def validate_custom_path(custom_path: str, base_dir: str) -> str:
    """Ensure path is within allowed directory."""
    if not custom_path:
        return None
    
    custom_path = Path(custom_path).resolve()
    base_dir = Path(base_dir).resolve()
    
    try:
        custom_path.relative_to(base_dir)
    except ValueError:
        raise ValueError(f"Path must be within {base_dir}")
    
    return str(custom_path)

# Then in api_download():
if custom_path:
    ALLOWED_DIR = os.path.expanduser("~/Downloads/AniWorld")  # Or configure this
    custom_path = validate_custom_path(custom_path.strip(), ALLOWED_DIR)
```

### 2. Missing Authorization on Sync Jobs
**Problem:** Any authenticated user can modify or delete other users' sync jobs.

**Fix needed in `api_update_sync_job()` and `api_delete_sync_job()`:**
```python
# Get the job first
job = self.db.get_sync_job(sync_job_id)
if not job:
    return jsonify({"error": "Sync job not found"}), 404

# Check ownership
if self.auth_enabled:
    current_user = self.db.get_user_by_session(request.cookies.get("session_token"))
    if job["created_by"] != current_user["id"]:
        return jsonify({"error": "Forbidden"}), 403
```

### 3. XSS in Cover URLs
**Problem:** Cover URLs are inserted into HTML without validation/escaping.

**Fix needed in `app.js`:**
```javascript
function validateUrl(url) {
    try {
        const parsed = new URL(url);
        return (parsed.protocol === 'http:' || parsed.protocol === 'https:') ? url : null;
    } catch {
        return null;
    }
}

// Before using coverUrl:
const safeCoverUrl = validateUrl(coverUrl) || 'default-image.png';
```

## 🟠 High Priority Issues

### 4. Missing CSRF Protection
**Quick fix in `app.py` line ~197:**
```python
response.set_cookie(
    "session_token",
    session_token,
    max_age=604800,
    httponly=True,
    secure=request.is_secure,  # Change from False
    samesite='Lax'  # Add this line
)
```

### 5. DateTime Bug
**Fix in `sync_manager.py` line ~96:**
```python
from datetime import timezone

# Change from:
return datetime.now() >= next_check

# To:
return datetime.now(timezone.utc) >= next_check
```

## 📋 Checklist

Before re-requesting review:
- [ ] Add path validation for `custom_path`
- [ ] Add ownership checks to sync job endpoints
- [ ] Validate/sanitize cover URLs in JavaScript
- [ ] Update cookie settings (secure + samesite)
- [ ] Fix timezone-aware datetime comparison

## 📄 Full Report

For complete details including:
- Proof-of-concept exploits
- CVSS scores
- Additional recommendations
- Testing guidelines

See: [PR_132_SECURITY_REVIEW.md](./PR_132_SECURITY_REVIEW.md)

## 💚 Positive Notes

Your code shows:
- Good threading/locking practices
- Clean structure and organization
- Useful feature implementations
- Proper logging

With these security fixes, this will be a great addition to the project! Let me know if you need any clarification on the fixes needed.
