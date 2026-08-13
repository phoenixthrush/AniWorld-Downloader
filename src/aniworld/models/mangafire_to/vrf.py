"""MangaFire API request signing."""

from base64 import b64decode, urlsafe_b64encode
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_STAGES = (
    (
        "yINlmUNho8VYJT+ibTIP+9ESiULpVEtMOoD6U6lRE0R/xwXo/Xp9NrUgC4cw/Lmo33vUyjUE40kUoEWIr/fxfNNcq2s79ShQ5NhNrFnJ4hXPwOu/SuXzIbuTQKGFvfm08E9jvCfqAtoDqvQq3dVWPQFmJjgvkISBeXY3BgANR+yVnjGbcxZ47d6kLNfZPIayTq3/YGySb1KuVZodWp/WGNAO5pfMcpaK53Hhs0allBszaMaxuouOwdxbwgxIw6YunSsXjI05Yi0j9j4eHKfSXR8Ifo/Od+8iamRfCXTyvm7NGRGYdcQ0ywcK/u6RXhrbcCm4t2eCtrDgQVecJGkQ+A==",
        "0Ec58JOY3uBzJK9m3zqIOpdlF7UFiax9DmA=",
        0x5A,
    ),
    (
        "IUFltCxD3Oc2cwCgkJffthaOg9cgPUb0LgW6H/VtfcF0kc5F25t+aWj6JH9VOhOaY0rAFdUxlDnl5BLNvwEJvQtP5qcw7vdb/K+chnbwnspSHT8mz5lqwz41TezG0hkO06FTjJZhsyNuFLDpD2ZZxQj/QIRcF90zpmQ7Byu483WsQqUE0C342HL+JXngRB6fRzxRyVTaKu83h7UYTJ0QMt6ixFh6S3F8gqkKwrGTL3jHNBsD45UnifK8+RGtishQV2K3rujLKEkiZxpr2dYcudFW4oFsDKhad3CLBvuyTqsCo4B7mL5IKQ1vXo/MOOvq1I1d8ar9X6Ttu5KF4fZgiA==",
        "AAdjb1iPY8CiDmq9H34tKTBF8a3oDQ==",
        0x35,
    ),
    (
        "NQHlu1/wVO5EmkwQymF810qqY2xG1k2obcas4Z9mCsPEIFl9pRIjFxbJ7ybMHbBckT5Ton85E0FOeHezbh/mjlEYpmpnlXOS8dgrqeq2KfxImTh1YK9y0PeMNhzA1OQzSY9brYOJq/l2QnE/hwOeZIhPixVSKIUlDb5vLcH6RWKxkIEMuP0bDwIqQ71AJJaEaMJL7A6YtyIwoRT+L5v4aZzodN/0+3nOGsfblFjgxSfPzVDjNFeNl5P26+kEC/8AHgdrpAbt3hHz3HrRN1Y6e+JHgF7ncFWnoF0y3THL1S71WgWGCa6KtSzTCCG58n68nTyj2T3Sshk7utqCtMi/ZQ==",
        "DELOJgPsVaCcblDtTGMdHzM=",
        0xBA,
    ),
)


def sign_url(url: str) -> str:
    """Add MangaFire's required VRF signature to an API URL."""
    parts = urlsplit(url)
    params = sorted(
        parse_qsl(parts.query, keep_blank_values=True), key=lambda item: item[0]
    )
    path = parts.path.removeprefix("/api")
    if params:
        indexes = {}
        query = []
        for key, value in params:
            if key.endswith("[]"):
                index = indexes.get(key, 0)
                indexes[key] = index + 1
                key = f"{key[:-2]}[{index}]"
            query.append(f"{key}={value}")
        path += "?" + "&".join(query)

    data = path.encode()
    for table, key, iv in _STAGES:
        table, key = b64decode(table), b64decode(key)
        output = bytearray()
        for index, value in enumerate(data):
            iv = table[(value ^ key[index % len(key)] ^ iv) & 0xFF]
            output.append(iv)
        data = output

    params.append(("vrf", urlsafe_b64encode(data).decode().rstrip("=")))
    return urlunsplit(parts._replace(query=urlencode(params)))
