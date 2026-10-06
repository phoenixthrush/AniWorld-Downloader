import logging
import os
import sys
from pathlib import Path

from .arguments import parse_args
from .config import ACTION_METHODS, ANIWORLD_CONFIG_DIR, VERSION
from .env import merge_env
from .logger import get_logger
from .models.common import run_each
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
    if (
        action not in {"watch", "syncplay"}
        or os.getenv("ANIWORLD_KEEP_WATCHING") != "1"
    ):
        return
    season = getattr(obj, "season", None)
    if season is None:
        return
    episodes = list(season.episodes)
    for index, episode in enumerate(episodes):
        if episode.url != obj.url:
            continue
        following = episodes[index + 1 :]
        for next_episode in following:
            for setting in ("selected_path", "selected_language", "selected_provider"):
                setattr(next_episode, setting, getattr(obj, setting))
        failures = run_each(following, action)
        if failures:
            raise RuntimeError(f"{len(failures)} following episode(s) failed")
        break


def model_for_url(url):
    provider = resolve_provider(url)
    # A video URL is one episode even when a site's franchise pattern overlaps.
    for pattern, model in (
        (provider.episode_pattern, provider.episode_cls),
        (provider.season_pattern, provider.season_cls),
        (provider.series_pattern, provider.series_cls),
    ):
        if pattern and pattern.fullmatch(url):
            return model(url=url)
    raise ValueError(f"Invalid URL for provider: {url}")


def aniworld():
    """Main entry point"""
    try:
        _enable_debug_logging_if_requested()
        logger.debug("Starting AniWorld-Downloader...")
        set_terminal_title()
        args = parse_args()

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
                obj = model_for_url(url)
                run_action(obj, action)

            return 0

        # ===== menu path =====
        # If multiple URLs are provided (e.g., via --episode-file), process them directly
        if args.episode_file and args.url:
            for url in args.url:
                obj = model_for_url(url)
                run_action(obj, action)
            return 0

        from .search import search

        url = args.url[0] if args.url else search()

        # FIX: replace s.to with serienstream.to to avoid issues with s.to being down
        url = url.replace("://s.to", "://serienstream.to")

        provider = resolve_provider(url)

        # If provider is NOT AniWorld -> bypass menu
        if provider.name != "AniWorld" and provider.name != "SerienStream":
            obj = model_for_url(url)
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
            built = []
            failures = []

            # Building an episode hits the network too, so a title that has gone
            # missing has to be survivable in the same way the action itself is.
            for episode_url in episodes:
                try:
                    built.append(
                        provider.episode_cls(
                            url=episode_url,
                            selected_path=selected_path,
                            selected_language=selected_language,
                            selected_provider=selected_provider,
                        )
                    )
                except Exception as exc:
                    logger.error("Could not load %s: %s", episode_url, exc)
                    failures.append((episode_url, exc))

            failures.extend(run_each(built, method_name))
            if failures:
                # Non-zero so scripts and cron jobs still notice an incomplete run
                return 1

        return 0

    except KeyboardInterrupt:
        print("\nQuitting.", file=sys.stderr)
        return 130

    except Exception as err:
        logger.exception("Unexpected error occurred")
        print(f"\nAn unexpected error occurred: {err}", file=sys.stderr)
        print("Please check the logs for more details.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(aniworld())
