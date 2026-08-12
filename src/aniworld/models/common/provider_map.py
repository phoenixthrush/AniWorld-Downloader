"""Map the host/provider names that streaming sites print onto the provider
keys the extractors are registered under (``get_direct_link_from_<key>``).

The German mirror sites label the same hoster in slightly different ways
("VOE", "Voe.SX", "DoodStream", "Dood", "Vidoza HD", …). This normalises them
so the download pipeline can find the matching extractor.
"""

try:
    from ...extractors import provider_functions
except ImportError:
    from aniworld.extractors import provider_functions

# Substrings checked against the lower-cased host/provider label.
# First match wins, so order the more specific entries first.
_ALIASES = (
    ("voe", "VOE"),
    ("dood", "Doodstream"),
    ("vidmoly", "Vidmoly"),
    ("vidoza", "Vidoza"),
    ("filemoon", "Filemoon"),
    ("streamtape", "Streamtape"),
    ("luluvdo", "Luluvdo"),
    ("loadx", "LoadX"),
    ("gxplayer", "MegaKino"),
)


def host_to_provider(label, require_extractor=True):
    """Return the canonical provider key for a host/provider `label`.

    Returns None when the label maps to no known hoster, or (when
    `require_extractor` is set) when no extractor is implemented for it.
    """
    text = (label or "").strip().lower()
    if not text:
        return None

    provider = None
    for needle, name in _ALIASES:
        if needle in text:
            provider = name
            break

    if provider is None:
        return None

    if (
        require_extractor
        and f"get_direct_link_from_{provider.lower()}" not in provider_functions
    ):
        return None

    return provider
