import re


def vidmoly_get_direct_link(soup):
    scripts = soup.find_all('script')
    file_link_pattern = r'file:\s*"(https?://.*?)"'

    for script in scripts:
        if script.string:
            match = re.search(file_link_pattern, script.string)
            if match:
                file_link = match.group(1)
                return file_link
    return None
