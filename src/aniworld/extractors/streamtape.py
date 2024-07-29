from re import compile


def streamtape_get_direct_link(soup):
    for tag in soup.find_all('script'):
        if "'robotlink')" in tag.text:
            match = compile(r"'robotlink'\)\.innerHTML = '(.+?)'\+ \('xcd(.+?)'\)").search(tag.text)
            if match:
                return "https:{}".format("".join(match.groups()))
    return None