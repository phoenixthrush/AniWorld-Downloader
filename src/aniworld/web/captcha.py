"""
Re-export captcha helpers from the playwright module so any code that imports
from ``aniworld.web.captcha`` (e.g. "Mein Aniworld" compatibility) works
without duplication.
"""

from ..playwright.captcha import (  # noqa: F401
    get_captcha_status,
    is_captcha_page,
    solve_captcha,
)
