# Security Review: PR #132 - Adding functions to webinterface

**Reviewer:** GitHub Copilot Code Review Agent  
**Date:** January 31, 2026  
**PR Author:** Domekologe (first-time contributor)  
**PR URL:** https://github.com/phoenixthrush/AniWorld-Downloader/pull/132

## Executive Summary

**⚠️ RECOMMENDATION: DO NOT MERGE WITHOUT SECURITY FIXES ⚠️**

This PR introduces valuable functionality (download cancellation, auto-sync, custom paths) but contains **3 critical security vulnerabilities** and **2 high-severity issues** that must be addressed before merging.

**Changes:** 7 files modified, +2091 lines, -136 lines  
**Severity Assessment:** Critical - Multiple security vulnerabilities found  
**Risk Level:** HIGH - Potential for unauthorized file system access and privilege escalation

---

## Critical Security Issues

### 🔴 Issue #1: Path Traversal Vulnerability

**Severity:** CRITICAL  
**CVSS Score:** ~7.5 (High)  
**CWE:** CWE-22 (Improper Limitation of a Pathname to a Restricted Directory)

#### Affected Files:
- `src/aniworld/web/app.py` (lines 682-686, 1027-1031)
- `src/aniworld/web/download_manager.py` (line 266)
- `src/aniworld/web/sync_manager.py` (line 136)

#### Description:
The `custom_path` parameter from user input is not validated before being used to construct file paths. An attacker can specify arbitrary paths on the filesystem.

#### Vulnerable Code:
```python
# app.py lines 682-686
custom_path = data.get("custom_path")
if custom_path:
    custom_path = custom_path.strip() or None  # ❌ Only strips whitespace!
else:
    custom_path = None

# download_manager.py line 266
if job.get("custom_path"):
    download_dir = str(job["custom_path"])  # ❌ Used directly without validation!
```

#### Attack Scenario:
1. Attacker sets `custom_path` to `/etc/` or `/tmp/` or any system directory
2. Downloads are written to that location
3. In `sync_manager.py`, the code scans directories with `.rglob("*")`, potentially exposing file metadata

#### Proof of Concept:
```javascript
// Malicious API call
fetch('/api/download', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        anime_url: "https://aniworld.to/anime/stream/some-anime",
        custom_path: "/etc/cron.d/"  // ❌ Arbitrary path!
    })
});
```

#### Recommended Fix:
```python
import os
from pathlib import Path

def validate_custom_path(custom_path: str, base_allowed_dir: str) -> str:
    """Validate that custom_path is within allowed directory."""
    if not custom_path:
        return None
    
    # Resolve to absolute path
    custom_path = Path(custom_path).resolve()
    base_allowed_dir = Path(base_allowed_dir).resolve()
    
    # Check if custom_path is under base_allowed_dir
    try:
        custom_path.relative_to(base_allowed_dir)
    except ValueError:
        raise ValueError(f"Path {custom_path} is not within allowed directory {base_allowed_dir}")
    
    return str(custom_path)

# Usage in app.py:
custom_path = data.get("custom_path")
if custom_path:
    try:
        # Define your allowed base directory (e.g., user's download folder)
        ALLOWED_BASE_DIR = os.path.expanduser("~/Downloads/AniWorld")
        custom_path = validate_custom_path(custom_path.strip(), ALLOWED_BASE_DIR)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
```

---

### 🔴 Issue #2: Missing Authorization Checks (IDOR)

**Severity:** CRITICAL  
**CVSS Score:** ~8.1 (High)  
**CWE:** CWE-639 (Authorization Bypass Through User-Controlled Key)

#### Affected Files:
- `src/aniworld/web/app.py` (lines 1142-1207, 1209-1234)

#### Description:
The API endpoints for updating and deleting sync jobs do not verify that the authenticated user owns the sync job they're trying to modify. This is an Insecure Direct Object Reference (IDOR) vulnerability.

#### Vulnerable Code:
```python
# app.py lines 1142-1150
@self.app.route("/api/sync/<int:sync_job_id>", methods=["PUT"])
@self._require_api_auth  # ❌ Only checks authentication, not authorization!
def api_update_sync_job(sync_job_id):
    """Update a sync job."""
    if not self.db:
        return jsonify({"success": False, "error": "Sync functionality not available"}), 400
    
    try:
        data = request.get_json()
        # ... directly updates without checking ownership! ❌
```

#### Attack Scenario:
1. User Alice creates sync job with ID 1
2. User Bob (authenticated) sends PUT request to `/api/sync/1`
3. Bob can modify Alice's sync job (change intervals, disable it, change paths, etc.)
4. Similarly, Bob can DELETE Alice's sync job

#### Recommended Fix:
```python
@self.app.route("/api/sync/<int:sync_job_id>", methods=["PUT"])
@self._require_api_auth
def api_update_sync_job(sync_job_id):
    """Update a sync job."""
    if not self.db:
        return jsonify({"success": False, "error": "Sync functionality not available"}), 400
    
    try:
        # ✅ Get the sync job first
        job = self.db.get_sync_job(sync_job_id)
        if not job:
            return jsonify({"error": "Sync job not found"}), 404
        
        # ✅ Verify ownership (if auth is enabled)
        if self.auth_enabled:
            current_user = self.db.get_user_by_session(request.cookies.get("session_token"))
            if not current_user:
                return jsonify({"error": "Unauthorized"}), 401
            
            # Allow if user owns the job OR user is admin
            if job["created_by"] != current_user["id"] and not current_user.get("is_admin", False):
                return jsonify({"error": "Forbidden: You don't own this sync job"}), 403
        
        # Now proceed with update...
        data = request.get_json()
        # ... rest of update logic
```

Apply similar fix to `api_delete_sync_job()` function.

---

### 🔴 Issue #3: Cross-Site Scripting (XSS)

**Severity:** CRITICAL  
**CVSS Score:** ~6.1 (Medium-High)  
**CWE:** CWE-79 (Improper Neutralization of Input During Web Page Generation)

#### Affected Files:
- `src/aniworld/web/static/js/app.js` (lines ~437, ~1283 in modified version)

#### Description:
The `coverUrl` variable is inserted into HTML without proper escaping. While typically from backend, if an attacker controls the cover URL, they can inject JavaScript.

#### Vulnerable Code Pattern:
```javascript
// Unescaped URL insertion
coverStyle = `style="background-image: url('${coverUrl}')"`;  // ❌

// Or:
html += `<img src="${coverUrl}" alt="${escapeHtml(anime.name)}">`;  // ❌ coverUrl not escaped!
```

#### Attack Scenario:
If an attacker can control the cover URL (through database manipulation or another vulnerability):
```javascript
coverUrl = "javascript:alert(document.cookie)";
// or
coverUrl = "' onerror='alert(document.cookie)";
```

#### Recommended Fix:
```javascript
function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function validateUrl(url) {
    // Only allow http/https URLs
    try {
        const parsed = new URL(url);
        if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
            return null;
        }
        return url;
    } catch {
        return null;
    }
}

// Usage:
const safeCoverUrl = validateUrl(coverUrl) || 'default-image.png';
coverStyle = `style="background-image: url('${escapeHtml(safeCoverUrl)}')"`;

// Better: Use DOM methods
const img = document.createElement('img');
img.src = safeCoverUrl;  // Browser automatically sanitizes
img.alt = escapeHtml(anime.name);
```

---

## High Severity Issues

### 🟠 Issue #4: Missing CSRF Protection

**Severity:** HIGH  
**CVSS Score:** ~6.5 (Medium)  
**CWE:** CWE-352 (Cross-Site Request Forgery)

#### Affected Files:
- `src/aniworld/web/app.py` (entire file, all POST/PUT/DELETE endpoints)

#### Description:
All state-changing API endpoints lack CSRF protection. The session cookie has no `SameSite` attribute, making CSRF attacks possible.

#### Attack Scenario:
Malicious website hosts code that triggers actions on behalf of logged-in users:
```html
<!-- Malicious site: evil.com -->
<script>
fetch('https://victim-aniworld.com/api/download', {
    method: 'POST',
    credentials: 'include',  // Sends session cookie
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        anime_url: "https://aniworld.to/anime/stream/malicious-anime",
        custom_path: "/tmp/hacked"
    })
});
</script>
```

#### Recommended Fix:
1. **Short-term:** Add `SameSite` attribute to cookies:
```python
# app.py line ~197
response.set_cookie(
    "session_token",
    session_token,
    max_age=604800,
    httponly=True,
    secure=True,  # Also fix this!
    samesite='Lax'  # ✅ Prevents CSRF
)
```

2. **Long-term:** Implement CSRF tokens:
```python
import secrets

class WebInterface:
    def generate_csrf_token(self):
        token = secrets.token_urlsafe(32)
        session_token = request.cookies.get("session_token")
        # Store mapping: session_token -> csrf_token
        return token
    
    def _require_csrf(self, f):
        def decorated_function(*args, **kwargs):
            csrf_token = request.headers.get('X-CSRF-Token')
            if not self.validate_csrf_token(csrf_token):
                return jsonify({"error": "Invalid CSRF token"}), 403
            return f(*args, **kwargs)
        return decorated_function
```

---

### 🟠 Issue #5: Insecure Cookie Configuration

**Severity:** HIGH  
**CVSS Score:** ~5.9 (Medium)  
**CWE:** CWE-614 (Sensitive Cookie in HTTPS Session Without 'Secure' Attribute)

#### Affected Files:
- `src/aniworld/web/app.py` (line 197)

#### Description:
Session cookie has `secure=False`, allowing transmission over unencrypted HTTP connections.

#### Vulnerable Code:
```python
# app.py line 197
response.set_cookie(
    "session_token",
    session_token,
    max_age=604800,
    httponly=True,
    secure=False  # ❌ Cookie sent over HTTP!
)
```

#### Attack Scenario:
1. User accesses application over HTTP
2. Session cookie transmitted in plaintext
3. Network attacker intercepts cookie
4. Attacker uses stolen cookie to impersonate user

#### Recommended Fix:
```python
response.set_cookie(
    "session_token",
    session_token,
    max_age=604800,
    httponly=True,
    secure=request.is_secure,  # ✅ Auto-detect HTTPS
    samesite='Lax'  # ✅ Also add this
)
```

Or enforce HTTPS:
```python
@self.app.before_request
def enforce_https():
    if not request.is_secure and not request.headers.get('X-Forwarded-Proto', 'http') == 'https':
        if app.config.get('ENFORCE_HTTPS', False):
            return redirect(request.url.replace('http://', 'https://'), 301)
```

---

## Medium Severity Issues

### 🟡 Issue #6: Timezone-Aware vs Naive DateTime Bug

**Severity:** MEDIUM (will cause runtime errors)  
**Files:** `src/aniworld/web/sync_manager.py` (lines 90-96)

#### Bug:
```python
# Line 90-92: Creates timezone-AWARE datetime
last_checked = datetime.fromisoformat(
    job["last_checked"].replace("Z", "+00:00")  # +00:00 makes it aware
)

# Line 96: Compares with timezone-NAIVE datetime
return datetime.now() >= next_check  # ❌ TypeError!
```

#### Fix:
```python
from datetime import timezone

last_checked = datetime.fromisoformat(
    job["last_checked"].replace("Z", "+00:00")
)
next_check = last_checked + timedelta(hours=check_interval)
return datetime.now(timezone.utc) >= next_check  # ✅ Both aware
```

---

### 🟡 Issue #7: Minor Race Condition

**Severity:** MEDIUM (mostly mitigated)  
**Files:** `src/aniworld/web/download_manager.py` (lines 163-179)

#### Description:
Small window where download status transitions during cancellation. Already mostly handled by defensive checks at lines 277-280 and 316-318.

#### Current (acceptable) mitigation:
```python
# Lines 277-280
with self._queue_lock:
    if queue_id not in self._active_downloads:  # ✅ Defensive check
        logging.info(f"Download {queue_id} cancelled during processing")
        return
```

**No urgent fix needed**, but could use a status flag instead of dict removal for cleaner state management.

---

## Summary of Required Changes

### Before Merging:
1. ✅ **Add path validation** for `custom_path` parameter
2. ✅ **Add authorization checks** to sync job update/delete endpoints  
3. ✅ **Sanitize/validate** `coverUrl` in JavaScript
4. ✅ **Add SameSite attribute** to session cookie
5. ✅ **Fix secure cookie** setting (use `request.is_secure`)
6. ✅ **Fix datetime comparison** in sync_manager.py

### Recommended (but optional):
- Add comprehensive CSRF token implementation
- Add rate limiting to API endpoints
- Add input validation for all user inputs
- Add logging for security events (failed auth, suspicious paths, etc.)

---

## Testing Recommendations

After fixes are applied, test:

1. **Path Traversal Test:**
   - Try setting custom_path to `/etc/`, `../../../etc/`, `C:\Windows\System32`
   - Verify all are rejected

2. **Authorization Test:**
   - Create sync job as User A
   - Try to modify/delete as User B
   - Verify 403 Forbidden response

3. **XSS Test:**
   - Inject `javascript:alert(1)` as coverUrl
   - Verify it's blocked or escaped

4. **CSRF Test:**
   - Try API calls from different origin without SameSite
   - Verify they're blocked

---

## Conclusion

This PR adds genuinely useful features but introduces serious security vulnerabilities. The issues are all **fixable with proper input validation and authorization checks**.

**Estimated Fix Time:** 2-4 hours for an experienced developer  
**Risk if Merged As-Is:** HIGH - Potential for data breaches and unauthorized access

**Final Recommendation:** Request changes from contributor with specific fixes outlined above, or apply fixes before merging.

---

## Positive Notes

Despite the security issues, the PR shows:
- ✅ Good feature implementation (download cancellation, auto-sync)
- ✅ Proper use of threading and locks in most places
- ✅ Reasonable database schema design
- ✅ Good logging practices
- ✅ Clean code structure

With security fixes applied, this would be a valuable addition to the project.
