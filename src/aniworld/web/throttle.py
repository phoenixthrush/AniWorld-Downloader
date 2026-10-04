"""Brute force protection for the local login form.

Failed logins are counted per client IP and per username inside a sliding
window. Once either count reaches its limit, further attempts are refused
until the oldest failure falls out of the window. Waitress serves the app from
a single process, so plain in-memory state shared between its threads is
enough; counters reset when the app restarts.
"""

import threading
import time
from collections import deque

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_IP = 10
MAX_FAILURES_PER_USER = 5

# Usernames are capped at 64 characters, anything longer is never valid and
# would only let a client grow the keys we keep in memory.
_MAX_KEY_LENGTH = 64
_PRUNE_INTERVAL = 60


class LoginThrottle:
    def __init__(
        self,
        window=WINDOW_SECONDS,
        max_per_ip=MAX_FAILURES_PER_IP,
        max_per_user=MAX_FAILURES_PER_USER,
        clock=time.monotonic,
    ):
        self.window = window
        self.max_per_ip = max_per_ip
        self.max_per_user = max_per_user
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = {}
        self._last_prune = clock()

    @staticmethod
    def _keys(ip, username):
        return ("ip", ip or ""), ("user", (username or "")[:_MAX_KEY_LENGTH])

    def _recent(self, key, now):
        failures = self._failures.get(key)
        if failures is None:
            return None
        while failures and failures[0] <= now - self.window:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return None
        return failures

    def _prune(self, now):
        if now - self._last_prune < _PRUNE_INTERVAL:
            return
        self._last_prune = now
        for key in list(self._failures):
            self._recent(key, now)

    def retry_after(self, ip, username):
        """Seconds until this client may try again, 0 when it is not blocked."""
        now = self._clock()
        wait = 0.0
        with self._lock:
            for key, limit in zip(
                self._keys(ip, username), (self.max_per_ip, self.max_per_user)
            ):
                failures = self._recent(key, now)
                if failures and len(failures) >= limit:
                    # Blocked until enough failures age out to drop below the limit
                    expires = failures[len(failures) - limit] + self.window
                    wait = max(wait, expires - now)
        return wait

    def record_failure(self, ip, username):
        """Count a failed attempt, returns True when it starts a lockout."""
        now = self._clock()
        locked = False
        with self._lock:
            self._prune(now)
            for key, limit in zip(
                self._keys(ip, username), (self.max_per_ip, self.max_per_user)
            ):
                failures = self._recent(key, now) or self._failures.setdefault(
                    key, deque()
                )
                failures.append(now)
                locked = locked or len(failures) == limit
        return locked

    def record_success(self, username):
        # The IP counter is left alone: one valid account must not reset the
        # budget for guessing the passwords of the others.
        with self._lock:
            self._failures.pop(self._keys(None, username)[1], None)
