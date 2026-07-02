import logging
import os
import sys
from pathlib import Path

from .arguments import parse_args
from .autodeps import ensure_patchright_chromium
from .config import ACTION_METHODS, ANIWORLD_CONFIG_DIR, VERSION
from .env import merge_env
from .logger import get_logger
from .providers import resolve_provider

merge_env(
    Path(__file__).resolve().parent / ".env.example",
    ANIWORLD_CONFIG_DIR / ".env",
)

logger = get_logger(__name__)


def _enable_debug_logging_if_requested():
    if "--debug" not in sys.argv and "-d" not in sys.argv:
        return

    os.environ["ANIWORLD_DEBUG_MODE"] = "1"
    logger.setLevel(logging.DEBUG)
    logging.getLogger().setLevel(logging.DEBUG)
    for name in logging.Logger.manager.loggerDict:
        logging.getLogger(name).setLevel(logging.DEBUG)
    logger.debug("Early debug mode enabled")


def set_terminal_title():
    """Set the terminal title if running in a TTY"""
    if sys.stdout.isatty():
        title = f"AniWorld-Downloader v.{VERSION}"
        print(f"\033]0;{title}\007", end="", flush=True)


def validate_action(action: str):
    if action not in ACTION_METHODS.values():
        raise ValueError(f"Invalid action: {action}")


def run_action(obj, action: str):
    validate_action(action)
    getattr(obj, action)()


def aniworld():
    """Main entry point"""
    try:
        _enable_debug_logging_if_requested()
        logger.debug("Starting AniWorld-Downloader...")
        set_terminal_title()
        args = parse_args()

        if not os.getenv("ANIWORLD_DOWNLOAD_PATH") == "/app/Downloads":
            logger.debug("Checking dependencies...")
            ensure_patchright_chromium()
            logger.debug("Dependencies OK")

        if args.web_ui:
            from .web import start_web_ui

            host = "0.0.0.0" if args.web_expose else "127.0.0.1"
            port = args.web_port
            open_browser = not args.no_browser
            force_sso = args.web_force_sso
            sso_enabled = args.web_sso or force_sso
            auth_enabled = args.web_auth or force_sso

            if sso_enabled:
                oidc_vars = [
                    "ANIWORLD_OIDC_ISSUER_URL",
                    "ANIWORLD_OIDC_CLIENT_ID",
                    "ANIWORLD_OIDC_CLIENT_SECRET",
                ]
                missing = [v for v in oidc_vars if not os.environ.get(v, "").strip()]
                if missing:
                    if force_sso:
                        print(
                            f"Error: --web-force-sso requires OIDC env vars: {', '.join(missing)}",
                            file=sys.stderr,
                        )
                        return 1
                    print(
                        f"Warning: --web-sso enabled but OIDC env vars not set: {', '.join(missing)}\n"
                        "SSO login will not be available. Set the variables in your .env file.",
                        file=sys.stderr,
                    )
                    sso_enabled = False

            start_web_ui(
                host=host,
                port=port,
                open_browser=open_browser,
                auth_enabled=auth_enabled,
                sso_enabled=sso_enabled,
                force_sso=force_sso,
            )
            return 0

        action = (args.action or "download").lower()

        # ===== no-menu path =====
        if os.getenv("ANIWORLD_NO_MENU") == "1":
            urls = args.url
            logger.debug(urls)

            if not urls:
                raise ValueError("No URLs provided while using --no-menu")

            for url in urls:
                provider = resolve_provider(url)

                if provider.series_pattern and provider.series_pattern.fullmatch(url):
                    obj = provider.series_cls(url=url)

                elif provider.season_pattern and provider.season_pattern.fullmatch(url):
                    obj = provider.season_cls(url=url)

                elif provider.episode_pattern and provider.episode_pattern.fullmatch(
                    url
                ):
                    obj = provider.episode_cls(url=url)

                else:
                    raise ValueError(f"Invalid URL for provider: {url}")

                run_action(obj, action)

            return 0

        # ===== menu path =====
        # If multiple URLs are provided (e.g., via --episode-file), process them directly
        if args.episode_file and args.url:
            for url in args.url:
                provider = resolve_provider(url)
                if provider.episode_pattern.fullmatch(url):
                    obj = provider.episode_cls(url=url)
                elif provider.season_pattern and provider.season_pattern.fullmatch(url):
                    obj = provider.season_cls(url=url)
                elif provider.series_pattern and provider.series_pattern.fullmatch(url):
                    obj = provider.series_cls(url=url)
                else:
                    raise ValueError(f"Invalid URL for provider: {url}")
                run_action(obj, action)
            return 0

        from .search import search

        url = args.url[0] if args.url else search()

        provider = resolve_provider(url)

        # If provider is NOT AniWorld -> bypass menu
        if provider.name != "AniWorld" and provider.name != "SerienStream":
            if provider.series_pattern and provider.series_pattern.fullmatch(url):
                obj = provider.series_cls(url=url)

            elif provider.season_pattern and provider.season_pattern.fullmatch(url):
                obj = provider.season_cls(url=url)

            elif provider.episode_pattern and provider.episode_pattern.fullmatch(url):
                obj = provider.episode_cls(url=url)

            else:
                raise ValueError(f"Invalid URL for provider: {url}")

            run_action(obj, action)
            return 0

        # If AniWorld but URL is episode OR season -> bypass menu too
        if provider.episode_pattern.fullmatch(url) or provider.season_pattern.fullmatch(
            url
        ):
            obj = (
                provider.episode_cls(url=url)
                if provider.episode_pattern.fullmatch(url)
                else provider.season_cls(url=url)
            )
            run_action(obj, action)
            return 0

        # AniWorld series -> show menu
        from .menu import app

        result = app(url=url)
        if not result:
            return 130

        action = result.get("action")
        episodes = result.get("episodes", [])
        selected_path = result.get("path")
        selected_language = result.get("language")
        selected_provider = result.get("provider")

        os.environ["ANIWORLD_ANISKIP"] = "1" if result.get("aniskip") else "0"

        if action in ACTION_METHODS:
            method_name = ACTION_METHODS[action]
            for episode_url in episodes:
                episode = provider.episode_cls(
                    url=episode_url,
                    selected_path=selected_path,
                    selected_language=selected_language,
                    selected_provider=selected_provider,
                )
                getattr(episode, method_name)()

        return 0

    except KeyboardInterrupt:
        print("\nQuitting.", file=sys.stderr)
        return 130

    except Exception as err:
        logger.error("Unexpected error occurred", exc_info=True)
        print(f"\nAn unexpected error occurred: {err}", file=sys.stderr)
        print("Please check the logs for more details.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(aniworld())
