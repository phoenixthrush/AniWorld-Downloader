"""Structured Moflix page data, using the existing HTTP/browser transport."""

import json
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .http import BASE_URL, get_response

# The recommendation endpoint returns HTTP 422 above this native result scope.
GENRE_API_LIMIT = 12


class MoflixResponseError(RuntimeError):
    """A public explanation of missing or malformed upstream data."""


def canonical_title_url(url):
    """Normalise a URL already accepted by MOFLIX_SERIES_PATTERN."""
    parsed = urlsplit(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) > 2 and parts[2].lower() != "season":
        del parts[2]
    parts[0] = "titles"
    if len(parts) > 2:
        parts[2] = "season"
    if len(parts) > 4:
        parts[4] = "episodes"
    return urlunsplit(
        ("https", "moflix-stream.xyz", "/" + "/".join(parts), parsed.query, "")
    )


def validate_response(response):
    text = response.text[:20000].lower()
    if response.headers.get("cf-mitigated") == "challenge" or any(
        marker in text
        for marker in (
            "<title>just a moment",
            "<title>attention required",
            "cf_chl_opt",
        )
    ):
        raise MoflixResponseError(
            "Moflix returned a verification page. Please try again later."
        )
    response.raise_for_status()
    return response


def parse_bootstrap(text):
    match = re.search(r"window\.bootstrapData\s*=\s*", text)
    if not match:
        raise MoflixResponseError("Moflix bootstrap data not found.")
    try:
        data, _ = json.JSONDecoder().raw_decode(text[match.end() :])
    except ValueError:
        raise MoflixResponseError("Moflix bootstrap data is invalid.") from None
    if not isinstance(data, dict):
        raise MoflixResponseError("Moflix bootstrap data has an invalid format.")
    return data


def page_loader(path, name):
    parsed = urlsplit(path)
    if not path.startswith("/") or parsed.scheme or parsed.netloc or parsed.fragment:
        raise MoflixResponseError("Invalid Moflix page path.")
    response = validate_response(get_response(BASE_URL + path))
    data = parse_bootstrap(response.text)
    loaders = data.get("loaders")
    loader = loaders.get(name) if isinstance(loaders, dict) else None
    if not isinstance(loader, dict):
        raise MoflixResponseError("Moflix page data is missing or has changed.")
    return loader


def read_json(response):
    validate_response(response)
    content_type = response.headers.get("Content-Type", "")
    if content_type and "json" not in content_type.lower():
        raise MoflixResponseError("Moflix returned a page instead of JSON data.")
    try:
        data = response.json()
    except ValueError:
        raise MoflixResponseError("Moflix returned invalid JSON data.") from None
    if not isinstance(data, dict):
        raise MoflixResponseError("Moflix returned an invalid data format.")
    return data


def title_cards(items, *, require_title=True):
    """Keep upstream order and the existing public {title, url, poster_url} shape."""
    if not isinstance(items, list):
        raise MoflixResponseError("Moflix title list has an invalid format.")
    results = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("model_type") not in (
            ("title",) if require_title else (None, "title")
        ):
            continue
        title_id = item.get("id")
        if isinstance(title_id, bool) or not re.fullmatch(r"[0-9]+", str(title_id)):
            continue
        title_id = str(title_id)
        name = item.get("name")
        if title_id in seen or not isinstance(name, str) or not name.strip():
            continue
        seen.add(title_id)
        poster = item.get("poster")
        poster = (
            urljoin(BASE_URL + "/", poster)
            if isinstance(poster, str) and poster
            else ""
        )
        if urlsplit(poster).scheme not in ("http", "https"):
            poster = ""
        results.append(
            {
                "title": name.strip(),
                "url": f"{BASE_URL}/titles/{title_id}",
                "poster_url": poster,
            }
        )
    return results


def paginated_items(url, key, get):
    """Follow increasing numeric page pointers on the original API endpoint."""
    items = []
    current_page = int(dict(parse_qsl(urlsplit(url).query)).get("page", "1"))
    for _ in range(100):
        data = read_json(get(url)).get(key)
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise MoflixResponseError(f"Moflix {key} list has an invalid format.")
        items.extend(data["data"])
        next_page = data.get("next_page")
        last_page = data.get("last_page")
        if last_page is not None and (
            isinstance(last_page, bool)
            or not re.fullmatch(r"[1-9][0-9]*", str(last_page))
        ):
            raise MoflixResponseError("Moflix returned invalid pagination.")
        if next_page is None:
            if last_page is not None and int(last_page) > current_page:
                next_page = current_page + 1
            else:
                return items
        if (
            isinstance(next_page, bool)
            or not re.fullmatch(r"[1-9][0-9]*", str(next_page))
            or int(next_page) <= current_page
        ):
            raise MoflixResponseError("Moflix returned invalid pagination.")
        current_page = int(next_page)
        parsed = urlsplit(url)
        params = [(k, v) for k, v in parse_qsl(parsed.query) if k != "page"]
        url = urlunsplit(
            parsed._replace(query=urlencode([*params, ("page", next_page)]))
        )
    raise MoflixResponseError("Moflix pagination exceeded its limit.")
