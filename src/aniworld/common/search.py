"""Shared options for site searches without site-specific genre lists."""


def validate_limit(limit):
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError("limit must be a non-negative integer or None.")


def limit_results(results, limit):
    return results[:limit]


def limit_reached(results, limit):
    return limit is not None and len(results) >= limit


def optional_filters(**filters):
    return {key: value for key, value in filters.items() if value not in (None, "")}
