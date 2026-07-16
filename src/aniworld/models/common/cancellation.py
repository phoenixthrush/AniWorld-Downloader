"""Instant cancellation for queue downloads.

The web queue worker registers the queue item it is currently downloading via
``begin()``/``end()``; the Flask cancel endpoint calls ``cancel(queue_id)``.
Download helpers poll ``raise_if_cancelled()`` between chunks/segments, and
every spawned ffmpeg process is registered so a cancel kills it mid-stream
instead of letting the current episode finish. CLI downloads never call
``begin()``, so every check is a no-op there.

Only one download runs at a time (single queue worker thread), so the state
is a single slot rather than a per-queue-id registry.
"""

import threading

__all__ = [
    "DownloadCancelledError",
    "begin",
    "cancel",
    "cancelled",
    "end",
    "raise_if_cancelled",
    "register_process",
    "unregister_process",
]


class DownloadCancelledError(Exception):
    """The user cancelled the queue item that is currently downloading."""


_lock = threading.Lock()
_state = {"queue_id": None, "event": None, "processes": set()}


def begin(queue_id):
    """Mark *queue_id* as the active, cancellable download."""
    with _lock:
        _state["queue_id"] = queue_id
        _state["event"] = threading.Event()
        _state["processes"] = set()


def end():
    """Clear the active download slot (call from a ``finally``)."""
    with _lock:
        _state["queue_id"] = None
        _state["event"] = None
        _state["processes"] = set()


def cancel(queue_id):
    """Request cancellation of the active download for *queue_id*.

    Sets the cancel flag and kills every registered process so ffmpeg stops
    immediately. Returns True when a matching download was active.
    """
    with _lock:
        if _state["queue_id"] != queue_id or _state["event"] is None:
            return False
        _state["event"].set()
        processes = list(_state["processes"])
    for process in processes:
        try:
            process.kill()
        except Exception:  # noqa: BLE001 - process may already be gone
            pass
    return True


def cancelled():
    """True when the active download has been cancelled."""
    event = _state["event"]
    return bool(event and event.is_set())


def raise_if_cancelled():
    """Raise ``DownloadCancelledError`` when the active download is cancelled."""
    if cancelled():
        raise DownloadCancelledError("Download cancelled by user")


def register_process(process):
    """Track a subprocess so ``cancel()`` can kill it.

    When cancellation already happened (races with process spawn), the process
    is killed on the spot.
    """
    kill_now = False
    with _lock:
        event = _state["event"]
        if event is None:
            return
        if event.is_set():
            kill_now = True
        else:
            _state["processes"].add(process)
    if kill_now:
        try:
            process.kill()
        except Exception:  # noqa: BLE001
            pass


def unregister_process(process):
    """Stop tracking a finished subprocess."""
    with _lock:
        _state["processes"].discard(process)
