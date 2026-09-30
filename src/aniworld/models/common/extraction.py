"""Shared stream resolution for models using registered hoster extractors."""


def resolve_stream_url(episode):
    """Resolve a provider URL and reject missing extractors or empty results."""
    from ...extractors import provider_functions

    provider = episode.selected_provider
    extractor = provider_functions.get(f"get_direct_link_from_{provider.lower()}")
    if extractor is None:
        raise ValueError(f"The provider '{provider}' is not yet implemented.")
    # Keep extractor failures separate from a missing registry entry.
    stream = extractor(episode.provider_url)
    if not isinstance(stream, str) or not stream:
        raise ValueError(f"Provider {provider} returned no stream URL")
    return stream
