import sys

try:
    from ...config import DEFAULT_USER_AGENT
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT


def get_direct_link_from_loadx(embeded_loadx_link, headers=None):
    """Get direct LoadX video URL."""
    raise NotImplementedError("get_direct_link_from_loadx is not implemented yet.")


def get_preview_image_link_from_loadx(embeded_loadx_link, headers=None):
    """Get LoadX preview image URL."""
    raise NotImplementedError(
        "get_preview_image_link_from_loadx is not implemented yet."
    )


if __name__ == "__main__":
    # Tested on xxxx/xx/xx -> WORKING
    # Example: https://xxx

    # logging.basicConfig(level=logging.DEBUG)

    link = input("Enter LoadX Link: ").strip()
    if not link:
        print("Error: No link provided")
        sys.exit(1)

    try:
        print("=" * 25)

        direct_link = get_direct_link_from_loadx(link)
        print("Direct link:", direct_link)
        print("=" * 25)

        print("Preview image:", get_preview_image_link_from_loadx(link))
        print("=" * 25)

        print(f'mpv "{direct_link}" --user-agent="{DEFAULT_USER_AGENT}"')

        print("=" * 25)
    except ValueError as e:
        print("Error:", e)
