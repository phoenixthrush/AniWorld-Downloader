"""Re-export the captcha helpers so `aniworld.web.captcha` keeps working.

Kept for external code (e.g. "Mein Aniworld") that imports from here.
"""

from ..playwright.captcha import (  # noqa: F401
    get_captcha_status,
    is_captcha_page,
    solve_captcha,
)
