"""Optional Discord request bot.

Users request a movie or series from Discord. The bot searches the real
streaming sites and shows the hits in a dropdown, so the requester picks the
exact title instead of a blind first-hit match. Depending on the mode the
request is either sent to the owner for approval (standard) or queued straight
away (advanced).

The module is import-safe: without discord.py installed, or with the bot turned
off, the web app keeps working and get_status() just reports it as unavailable.
"""

import asyncio
import os
import threading

from ..logger import get_logger
from ..providers import resolve_provider
from . import db
from .media import SITE_LABELS
from .sitesearch import aggregate

logger = get_logger(__name__)

try:
    import discord
    from discord import app_commands

    DISCORD_AVAILABLE = True
except Exception:  # optional dependency
    DISCORD_AVAILABLE = False

MOVIE_LANGUAGES = ("German Dub", "English Dub")
SERIES_LANGUAGES = ("German Dub", "English Dub", "English Sub", "German Sub")

# How long a request's dropdown stays usable.
VIEW_TIMEOUT = 300

TRANSLATIONS = {
    "en": {
        "cmd_movie": "movie-request",
        "cmd_movie_desc": "Request a movie",
        "cmd_series": "series-request",
        "cmd_series_desc": "Request a series",
        "arg_movie_title": "Movie title",
        "arg_series_title": "Series title",
        "no_permission": "You don't have permission to request.",
        "search_failed": "Search failed: {error}",
        "no_results": "No results found for **{title}**.",
        "results_for": "Results for **{title}**:",
        "pick_title": "Pick the exact title",
        "language_ph": "Language",
        "choose_language": "**{title}** - choose a language:",
        "queued": "✅ **{title}** ({language}) was added to the download queue.",
        "queue_failed": "❌ Could not queue **{title}**: {error}",
        "no_owner": "⚠️ No owner is configured, so the request can't be forwarded.",
        "sent_for_approval": "\U0001f4e8 Your request for **{title}** was sent for approval.",
        "owner_unreachable": "⚠️ Could not reach the owner via DM.",
        "req_title": "New download request",
        "f_type": "Type",
        "f_language": "Language",
        "f_site": "Site",
        "f_requested_by": "Requested by",
        "f_url": "URL",
        "btn_accept": "Accept",
        "btn_decline": "Decline",
        "accepted_owner": "✅ Accepted - **{title}** is downloading.",
        "accepted_dm": "✅ Your request **{title}** was accepted and is downloading.",
        "decline_title": "Decline request",
        "decline_reason": "Reason (optional)",
        "declined_owner": "\U0001f6ab Declined **{title}**.",
        "declined_dm": "\U0001f6ab Your request **{title}** was declined.",
        "declined_reason": "Reason: {reason}",
        "queue_failed_short": "❌ Failed to queue: {error}",
        "available_dm": "✅ Your request **{title}** has finished downloading and is now available.",
        "available_title": "{title} is now available!",
        "available_desc": "**{title}** ({language}) has finished downloading and is now available.",
        "type_movie": "Movie",
        "type_series": "Series",
        "lang_german": "German",
        "lang_english": "English",
        "qual_dub": "Dub",
        "qual_sub": "Sub",
    },
    "de": {
        "cmd_movie": "film-anfrage",
        "cmd_movie_desc": "Einen Film anfragen",
        "cmd_series": "serien-anfrage",
        "cmd_series_desc": "Eine Serie anfragen",
        "arg_movie_title": "Filmtitel",
        "arg_series_title": "Serientitel",
        "no_permission": "Du hast keine Berechtigung, etwas anzufragen.",
        "search_failed": "Suche fehlgeschlagen: {error}",
        "no_results": "Keine Ergebnisse für **{title}** gefunden.",
        "results_for": "Ergebnisse für **{title}**:",
        "pick_title": "Wähle den genauen Titel",
        "language_ph": "Sprache",
        "choose_language": "**{title}** - wähle eine Sprache:",
        "queued": "✅ **{title}** ({language}) wurde zur Download-Warteschlange hinzugefügt.",
        "queue_failed": "❌ **{title}** konnte nicht eingereiht werden: {error}",
        "no_owner": "⚠️ Es ist kein Owner konfiguriert, daher kann die Anfrage nicht weitergeleitet werden.",
        "sent_for_approval": "\U0001f4e8 Deine Anfrage für **{title}** wurde zur Freigabe gesendet.",
        "owner_unreachable": "⚠️ Der Owner konnte per DM nicht erreicht werden.",
        "req_title": "Neue Download-Anfrage",
        "f_type": "Typ",
        "f_language": "Sprache",
        "f_site": "Seite",
        "f_requested_by": "Angefragt von",
        "f_url": "URL",
        "btn_accept": "Annehmen",
        "btn_decline": "Ablehnen",
        "accepted_owner": "✅ Angenommen - **{title}** wird heruntergeladen.",
        "accepted_dm": "✅ Deine Anfrage **{title}** wurde angenommen und wird heruntergeladen.",
        "decline_title": "Anfrage ablehnen",
        "decline_reason": "Grund (optional)",
        "declined_owner": "\U0001f6ab **{title}** abgelehnt.",
        "declined_dm": "\U0001f6ab Deine Anfrage **{title}** wurde abgelehnt.",
        "declined_reason": "Grund: {reason}",
        "queue_failed_short": "❌ Einreihen fehlgeschlagen: {error}",
        "available_dm": "✅ Deine Anfrage **{title}** ist fertig heruntergeladen und jetzt verfügbar.",
        "available_title": "{title} ist jetzt verfügbar!",
        "available_desc": "**{title}** ({language}) wurde fertig heruntergeladen und ist jetzt verfügbar.",
        "type_movie": "Film",
        "type_series": "Serie",
        "lang_german": "Deutsch",
        "lang_english": "Englisch",
        "qual_dub": "Dub",
        "qual_sub": "Sub",
    },
}


def t(config, key, **kwargs):
    language = (config or {}).get("language", "en")
    if language not in TRANSLATIONS:
        language = "en"
    text = TRANSLATIONS[language].get(key) or TRANSLATIONS["en"].get(key, key)
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError):
        return text


def _language_label(config, value, media_type):
    """Movies only ever come as a dub, so drop the qualifier there."""
    name = t(config, "lang_german" if value.startswith("German") else "lang_english")
    if media_type == "movie":
        return name
    return f"{name} ({t(config, 'qual_dub' if value.endswith('Dub') else 'qual_sub')})"


# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------
_state = {
    "thread": None,
    "loop": None,
    "client": None,
    "running": False,
    "error": None,
    "user": None,
    "config": None,
}
_lock = threading.Lock()


def read_config():
    return {
        "enabled": os.environ.get("ANIWORLD_DISCORD_BOT_ENABLED", "0") == "1",
        "token": os.environ.get("ANIWORLD_DISCORD_TOKEN", "").strip(),
        "owner_id": os.environ.get("ANIWORLD_DISCORD_OWNER_ID", "").strip(),
        "mode": os.environ.get("ANIWORLD_DISCORD_MODE", "standard").strip().lower(),
        "role_id": os.environ.get("ANIWORLD_DISCORD_REQUEST_ROLE_ID", "").strip(),
        "guild_id": os.environ.get("ANIWORLD_DISCORD_GUILD_ID", "").strip(),
        "language": os.environ.get("ANIWORLD_DISCORD_LANGUAGE", "en").strip().lower(),
        "announce_channel_id": os.environ.get(
            "ANIWORLD_DISCORD_ANNOUNCE_CHANNEL_ID", ""
        ).strip(),
    }


def get_status():
    with _lock:
        return {
            "available": DISCORD_AVAILABLE,
            "running": _state["running"],
            "error": _state["error"],
            "user": _state["user"],
        }


def _default_provider():
    return os.environ.get("ANIWORLD_PROVIDER", "VOE").strip() or "VOE"


def _enqueue(title, url, media_type, language, provider, requester, requester_id):
    """Blocking: resolves the series and writes to sqlite, run in an executor."""
    if media_type == "movie":
        episodes = [url]
    else:
        series = resolve_provider(url).series_cls(url=url)
        episodes = [
            episode.url for season in series.seasons for episode in season.episodes
        ]
        if not episodes:
            raise RuntimeError("no episodes found for series")

    db.add_to_queue(
        title=title,
        series_url=url,
        episodes=episodes,
        language=language,
        provider=provider,
        username=requester,
        source="discord",
        discord_user_id=requester_id,
    )


# ---------------------------------------------------------------------------
# Completion notice (called from the queue worker thread)
# ---------------------------------------------------------------------------
def notify_completed(title, media_type, language, discord_user_id):
    """Schedule a DM (and optional announcement) on the bot's own event loop."""
    with _lock:
        loop, client, config = _state["loop"], _state["client"], _state["config"]
    if not (loop and client and loop.is_running()):
        return
    try:
        asyncio.run_coroutine_threadsafe(
            _announce(client, config, title, media_type, language, discord_user_id),
            loop,
        )
    except Exception as exc:
        logger.info("Discord: could not schedule completion notice: %s", exc)


async def _announce(client, config, title, media_type, language, user_id):
    if user_id:
        try:
            user = await client.fetch_user(int(user_id))
            await user.send(t(config, "available_dm", title=title))
        except Exception as exc:
            logger.info("Discord: could not DM requester on completion: %s", exc)

    channel_id = (config or {}).get("announce_channel_id")
    if not channel_id:
        return
    try:
        channel = client.get_channel(int(channel_id)) or await client.fetch_channel(
            int(channel_id)
        )
        embed = discord.Embed(
            title=t(config, "available_title", title=title),
            description=t(config, "available_desc", title=title, language=language),
            color=0x22C55E,
        )
        type_key = "type_movie" if media_type == "movie" else "type_series"
        embed.add_field(
            name=t(config, "f_type"), value=t(config, type_key), inline=True
        )
        embed.add_field(name=t(config, "f_language"), value=language, inline=True)
        await channel.send(embed=embed)
    except Exception as exc:
        logger.warning("Discord: announce to channel failed: %s", exc)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
def _build_client(config):
    client = discord.Client(intents=discord.Intents.default())
    tree = app_commands.CommandTree(client)

    async def run_blocking(func, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func, *args)

    def allowed(interaction):
        if not config["role_id"]:
            return True
        roles = getattr(interaction.user, "roles", None) or []
        return any(str(role.id) == config["role_id"] for role in roles)

    async def owner_user():
        if not config["owner_id"]:
            return None
        try:
            return await client.fetch_user(int(config["owner_id"]))
        except Exception as exc:
            logger.warning("Discord: could not fetch owner: %s", exc)
            return None

    async def edit(interaction, content):
        try:
            await interaction.response.edit_message(content=content, view=None)
        except Exception:
            try:
                await interaction.edit_original_response(content=content, view=None)
            except Exception:
                pass

    async def dm_requester(ctx, message):
        try:
            user = await client.fetch_user(int(ctx["requester_id"]))
            await user.send(message)
        except Exception as exc:
            logger.info("Discord: could not DM requester: %s", exc)

    class LanguageSelect(discord.ui.Select):
        def __init__(self, ctx):
            self.ctx = ctx
            media_type = ctx["media_type"]
            languages = MOVIE_LANGUAGES if media_type == "movie" else SERIES_LANGUAGES
            super().__init__(
                placeholder=t(config, "language_ph"),
                options=[
                    discord.SelectOption(
                        label=_language_label(config, language, media_type),
                        value=language,
                    )
                    for language in languages
                ],
            )

        async def callback(self, interaction):
            self.ctx["language"] = self.values[0]
            self.ctx["provider"] = _default_provider()
            if config["mode"] == "advanced":
                await do_enqueue(interaction, self.ctx)
            else:
                await request_approval(interaction, self.ctx)

    class ResultSelect(discord.ui.Select):
        def __init__(self, ctx, results):
            self.ctx = ctx
            self.results = results[:25]
            super().__init__(
                placeholder=t(config, "pick_title"),
                options=[
                    discord.SelectOption(
                        label=(item.get("title") or "Unknown")[:80],
                        description=SITE_LABELS.get(item.get("site", ""), ""),
                        value=str(index),
                    )
                    for index, item in enumerate(self.results)
                ],
            )

        async def callback(self, interaction):
            chosen = self.results[int(self.values[0])]
            self.ctx["title"] = chosen.get("title") or self.ctx["title"]
            self.ctx["url"] = chosen["url"]
            self.ctx["site"] = chosen.get("site", "")
            view = discord.ui.View(timeout=VIEW_TIMEOUT)
            view.add_item(LanguageSelect(self.ctx))
            await interaction.response.edit_message(
                content=t(config, "choose_language", title=self.ctx["title"]), view=view
            )

    async def do_enqueue(interaction, ctx):
        try:
            await run_blocking(
                _enqueue,
                ctx["title"],
                ctx["url"],
                ctx["media_type"],
                ctx["language"],
                ctx["provider"],
                ctx["requester_name"],
                ctx["requester_id"],
            )
        except Exception as exc:
            logger.error("Discord enqueue failed: %s", exc)
            await edit(
                interaction, t(config, "queue_failed", title=ctx["title"], error=exc)
            )
            return
        await edit(
            interaction,
            t(config, "queued", title=ctx["title"], language=ctx["language"]),
        )

    async def request_approval(interaction, ctx):
        owner = await owner_user()
        if owner is None:
            await edit(interaction, t(config, "no_owner"))
            return

        embed = discord.Embed(
            title=t(config, "req_title"),
            description=f"**{ctx['title']}**",
            color=0x2563EB,
        )
        type_key = "type_movie" if ctx["media_type"] == "movie" else "type_series"
        embed.add_field(
            name=t(config, "f_type"), value=t(config, type_key), inline=True
        )
        embed.add_field(
            name=t(config, "f_language"), value=ctx["language"], inline=True
        )
        embed.add_field(
            name=t(config, "f_site"),
            value=SITE_LABELS.get(ctx.get("site", ""), ctx.get("site", "")),
            inline=True,
        )
        embed.add_field(
            name=t(config, "f_requested_by"), value=ctx["requester_name"], inline=False
        )
        embed.add_field(name=t(config, "f_url"), value=ctx["url"], inline=False)

        try:
            await owner.send(embed=embed, view=ApprovalView(ctx))
        except Exception as exc:
            logger.error("Discord: could not DM owner: %s", exc)
            await edit(interaction, t(config, "owner_unreachable"))
            return
        await edit(interaction, t(config, "sent_for_approval", title=ctx["title"]))

    class ApprovalView(discord.ui.View):
        def __init__(self, ctx):
            super().__init__(timeout=None)
            self.ctx = ctx

        @discord.ui.button(
            label=t(config, "btn_accept"), style=discord.ButtonStyle.success
        )
        async def accept(self, interaction, button):
            try:
                await run_blocking(
                    _enqueue,
                    self.ctx["title"],
                    self.ctx["url"],
                    self.ctx["media_type"],
                    self.ctx["language"],
                    self.ctx["provider"],
                    self.ctx["requester_name"],
                    self.ctx["requester_id"],
                )
            except Exception as exc:
                await interaction.response.edit_message(
                    content=t(config, "queue_failed_short", error=exc), view=None
                )
                return
            await interaction.response.edit_message(
                content=t(config, "accepted_owner", title=self.ctx["title"]), view=None
            )
            await dm_requester(
                self.ctx, t(config, "accepted_dm", title=self.ctx["title"])
            )

        @discord.ui.button(
            label=t(config, "btn_decline"), style=discord.ButtonStyle.danger
        )
        async def decline(self, interaction, button):
            await interaction.response.send_modal(DeclineModal(self.ctx))

    class DeclineModal(discord.ui.Modal):
        def __init__(self, ctx):
            super().__init__(title=t(config, "decline_title"))
            self.ctx = ctx
            self.reason = discord.ui.TextInput(
                label=t(config, "decline_reason"),
                required=False,
                style=discord.TextStyle.paragraph,
            )
            self.add_item(self.reason)

        async def on_submit(self, interaction):
            await interaction.response.edit_message(
                content=t(config, "declined_owner", title=self.ctx["title"]), view=None
            )
            message = t(config, "declined_dm", title=self.ctx["title"])
            reason = str(self.reason.value or "").strip()
            if reason:
                message += "\n" + t(config, "declined_reason", reason=reason)
            await dm_requester(self.ctx, message)

    async def start_request(interaction, title, media_type):
        if not allowed(interaction):
            await interaction.response.send_message(
                t(config, "no_permission"), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            results = await run_blocking(aggregate, title, media_type)
        except Exception as exc:
            await interaction.followup.send(
                t(config, "search_failed", error=exc), ephemeral=True
            )
            return
        if not results:
            await interaction.followup.send(
                t(config, "no_results", title=title), ephemeral=True
            )
            return

        ctx = {
            "title": title,
            "media_type": media_type,
            "requester_id": str(interaction.user.id),
            "requester_name": str(interaction.user),
        }
        view = discord.ui.View(timeout=VIEW_TIMEOUT)
        view.add_item(ResultSelect(ctx, results))
        await interaction.followup.send(
            content=t(config, "results_for", title=title), view=view, ephemeral=True
        )

    @tree.command(name=t(config, "cmd_movie"), description=t(config, "cmd_movie_desc"))
    @app_commands.describe(title=t(config, "arg_movie_title"))
    async def movie_request(interaction, title: str):
        await start_request(interaction, title, "movie")

    @tree.command(
        name=t(config, "cmd_series"), description=t(config, "cmd_series_desc")
    )
    @app_commands.describe(title=t(config, "arg_series_title"))
    async def series_request(interaction, title: str):
        await start_request(interaction, title, "series")

    @client.event
    async def on_ready():
        with _lock:
            _state.update(running=True, error=None, user=str(client.user))
        try:
            if config["guild_id"]:
                guild = discord.Object(id=int(config["guild_id"]))
                tree.copy_global_to(guild=guild)
                await tree.sync(guild=guild)
                # Drop stale global commands left by a previous bot on this token
                tree.clear_commands(guild=None)
                await tree.sync()
            else:
                await tree.sync()
        except Exception as exc:
            logger.warning("Discord: command sync failed: %s", exc)
        logger.info("Discord bot ready as %s", client.user)

    # The stop path needs these to unregister the commands again
    client.aniworld_tree = tree
    client.aniworld_guild_id = config["guild_id"]
    return client


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def _run_bot(config):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    with _lock:
        _state["loop"] = loop

    client = _build_client(config)
    with _lock:
        _state["client"] = client

    try:
        loop.run_until_complete(client.start(config["token"]))
    except Exception as exc:
        logger.error("Discord bot stopped: %s", exc)
        with _lock:
            _state["error"] = str(exc)[:120]
    finally:
        try:
            loop.run_until_complete(client.close())
        except Exception:
            pass
        loop.close()
        with _lock:
            _state.update(running=False, loop=None, client=None, user=None)


async def _clear_commands(client):
    tree = getattr(client, "aniworld_tree", None)
    if tree is None:
        return
    tree.clear_commands(guild=None)
    await tree.sync()
    guild_id = getattr(client, "aniworld_guild_id", "")
    if guild_id:
        guild = discord.Object(id=int(guild_id))
        tree.clear_commands(guild=guild)
        await tree.sync(guild=guild)


def _stop_locked():
    client, loop, thread = _state["client"], _state["loop"], _state["thread"]
    if client and loop and loop.is_running():
        # Unregister the slash commands first so nothing lingers while it is off
        try:
            asyncio.run_coroutine_threadsafe(_clear_commands(client), loop).result(
                timeout=20
            )
        except Exception as exc:
            logger.warning("Discord: clearing commands on stop failed: %s", exc)
        asyncio.run_coroutine_threadsafe(client.close(), loop)
    if thread and thread.is_alive():
        thread.join(timeout=10)
    _state.update(thread=None, running=False, config=None)


def reconcile():
    """Start, stop or restart the bot so it matches the current configuration."""
    if not DISCORD_AVAILABLE:
        with _lock:
            _state["error"] = "discord.py not installed"
        return

    config = read_config()
    with _lock:
        running = _state["thread"] is not None and _state["thread"].is_alive()
        should_run = config["enabled"] and bool(config["token"])

        if not should_run:
            if running:
                _stop_locked()
            _state["error"] = None
            return

        if running and _state["config"] == config:
            return
        if running:
            _stop_locked()

        _state["config"] = config
        _state["error"] = None
        thread = threading.Thread(target=_run_bot, args=(config,), daemon=True)
        _state["thread"] = thread
        thread.start()


def start_if_enabled():
    try:
        reconcile()
    except Exception as exc:
        logger.error("Discord bot start failed: %s", exc)
