import re


def streamtape_get_direct_link(soup):
    for tag in soup.find_all('script'):
        if "'robotlink')" in tag.text:
            pattern = r"'robotlink'\)\.innerHTML = '(.+?)'\+ \('xcd(.+?)'\)"
            match = re.compile(pattern).search(tag.text)
            if match:
                return f"https:{''.join(match.groups())}"
    return None
