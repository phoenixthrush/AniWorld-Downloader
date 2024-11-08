from re import search


def vidoza_get_direct_link(soup):
    for tag in soup.find_all('script'):
        if 'sourcesCode:' in tag.text:
            match = search(r'src: "(.*?)"', tag.text)
            if match:
                return match.group(1)
    return None
