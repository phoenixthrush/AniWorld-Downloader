"""DubSync: graft a web-sourced German dub onto archive-quality video files.

``run_dubsync`` is exported lazily so that importing the pure-stdlib
:mod:`matcher` (and its unit tests) does not pull in ffmpeg / config.
"""

from .matcher import MatchReport, match_directory

__all__ = [
    "run_dubsync",
    "match_directory",
    "MatchReport",
    "detect_offset",
    "AlignResult",
]


def __getattr__(name):
    if name == "run_dubsync":
        from .pipeline import run_dubsync

        return run_dubsync
    if name in ("detect_offset", "AlignResult"):
        from . import align

        return getattr(align, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
