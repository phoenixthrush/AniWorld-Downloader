from types import SimpleNamespace

import pytest

from aniworld import search
from aniworld.extractors.provider import hanime_tv

QUERIES = [
    (search.fetch_genre_animes, {"slug": "action"}),
    (search.query_s_to, {"genre": "action"}),
    (search.query_burningseries, {"genre": "Action"}),
    (search.query_kinox, {"genre": "Action"}),
    (hanime_tv.search_hanime, {"genre": "fantasy"}),
    (search.query_filmo, {"genre_id": 1}),
    (search.query_filmpalast, {"genre": "Action"}),
    (search.query_megakino, {"genre": "action"}),
]


@pytest.mark.parametrize("query,kwargs", QUERIES)
@pytest.mark.parametrize("limit", [-1, 1.5, "10", True])
def test_invalid_limits_fail_before_fetch(query, kwargs, limit):
    with pytest.raises(ValueError, match="limit must be"):
        query(**kwargs, limit=limit)


@pytest.mark.parametrize("query,kwargs", QUERIES)
def test_zero_limit_skips_fetch(query, kwargs):
    result = query(**kwargs, limit=0)
    assert (result["results"] if isinstance(result, dict) else result) == []


@pytest.mark.parametrize("query,kwargs", QUERIES)
def test_limits_apply_to_each_backend(monkeypatch, query, kwargs):
    rows = "".join(
        f'<div data-group="shows"><a href="/serie/item-{n}"></a><h6 class="show-title">Item {n}</h6></div>'
        f'<article class="liste"><h2><a href="/stream/item-{n}">Item {n}</a></h2></article>'
        f'<a href="/movies/item-{n}"><h3 class="movie-poster-grid-card__title">Item {n}</h3></a>'
        f'<td class="Title"><a href="/Stream/item-{n}.html">Item {n}</a></td>'
        f'<a href="/videos/hentai/item-{n}"><img alt="Item {n}" src="p.jpg"></a>'
        for n in range(5)
    )
    response = SimpleNamespace(text=rows, raise_for_status=lambda: None)
    from aniworld.models.s_to import http

    monkeypatch.setattr(search.GLOBAL_SESSION, "get", lambda *a, **k: response)
    monkeypatch.setattr(http, "sto_get", lambda *a, **k: response)
    monkeypatch.setattr(hanime_tv, "_request_hanime", lambda *a, **k: response)
    monkeypatch.setattr(
        search, "_fetch_megakino_page", lambda path: (rows, "https://megakino.example")
    )
    monkeypatch.setattr(
        search,
        "_extract_megakino_cards",
        lambda *a: [(str(n), f"https://megakino.example/{n}", "") for n in range(5)],
    )
    monkeypatch.setattr(
        search, "_parse_cover_items", lambda *a: [{"title": str(n)} for n in range(5)]
    )
    monkeypatch.setattr(
        search,
        "_bs_index_cache",
        '<div class="genre"><span><strong>Action</strong></span><ul>'
        + "".join(f'<a href="serie/item-{n}">Item {n}</a>' for n in range(5))
        + "</ul></div>",
    )
    for limit in (2, None):
        result = query(**kwargs, limit=limit)
        assert len(result["results"] if isinstance(result, dict) else result) == (
            2 if limit else 5
        )


@pytest.mark.parametrize(
    "query,kwargs",
    [(search.query_s_to, {"genre": "action"}), (search.query_filmo, {"genre_id": 1})],
)
def test_pagination_stops_when_limit_reached(monkeypatch, query, kwargs):
    from aniworld.models.s_to import http

    calls = []
    page = '<div data-group="shows"><a href="/serie/one"></a><h6 class="show-title">One</h6><a rel="next" href="?page=2">Next</a></div><a href="/movies/one"><h3 class="movie-poster-grid-card__title">One</h3></a>'

    def get(*a, **k):
        calls.append(a)
        return SimpleNamespace(text=page, raise_for_status=lambda: None)

    monkeypatch.setattr(search.GLOBAL_SESSION, "get", get)
    monkeypatch.setattr(http, "sto_get", get)
    assert len(query(**kwargs, limit=1)) == 1
    assert len(calls) == 1
