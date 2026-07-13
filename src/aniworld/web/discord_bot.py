"""Optional Discord request bot.

Users request a movie or series from Discord. The bot searches the actual
streaming site and shows the real hits in a dropdown, so the requester picks
the exact title — this is why it can never grab "the wrong movie" the way a
blind first-hit matcher would. Depending on the configured mode the request is
either sent to the owner for approval (standard) or queued straight away
(advanced).

The bot speaks English or German (ANIWORLD_DISCORD_LANGUAGE): the slash command
names, their descriptions and every message it sends follow that setting. When a
requested download finishes, the requester is always DM'd, and — if an announce
channel is configured — a "now available" message is posted there too.

The whole module is import-safe: if discord.py is not installed, or the bot is
disabled, the web app keeps working and `get_status()` simply reports it as off.
"""

import asyncio
import os
import threading

from ..logger import get_logger
from ..providers import resolve_provider
from .db import add_to_queue
from .planned import search_site, sites_for

logger = get_logger(__name__)

try:
    import discord
    from discord import app_commands

    DISCORD_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    DISCORD_AVAILABLE = False


# Nice labels for the aggregated dropdown.
SITE_LABELS = {
    "aniworld": "AniWorld",
    "sto": "SerienStream",
    "megakino": "MegaKino",
    "kinox": "Kinox",
    "filmpalast": "FilmPalast",
    "burningseries": "BurningSeries",
    "cineby": "Cineby",
}


# ---------------------------------------------------------------------------
# Localisation
# ---------------------------------------------------------------------------
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
        "choose_language": "**{title}** — choose a language:",
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
        "accepted_owner": "✅ Accepted — **{title}** is downloading.",
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
        "choose_language": "**{title}** — wähle eine Sprache:",
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
        "accepted_owner": "✅ Angenommen — **{title}** wird heruntergeladen.",
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


def _lang_option_label(config, value, media_type):
    """Friendly, localised label for a language option.

    Movies only ever come as a dub, so we drop the "Dub" qualifier there and show
    just the language name (Deutsch/English/…). Series keep a (Dub)/(Sub) suffix
    so the two variants stay distinguishable. The option's *value* is unchanged —
    it's still the real "German Dub"/"English Sub"/… string the downloader needs.
    """
    base = "lang_german" if value.startswith("German") else "lang_english"
    name = t(config, base)
    if media_type == "movie":
        return name
    qual = "qual_dub" if value.endswith("Dub") else "qual_sub"
    return f"{name} ({t(config, qual)})"


def _lang(config):
    lang = (config or {}).get("language", "en")
    return lang if lang in TRANSLATIONS else "en"


def t(config, key, **kwargs):
    text = TRANSLATIONS[_lang(config)].get(key, TRANSLATIONS["en"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def aggregate_search(title, media_type):
    """Search every site of `media_type` and return combined, site-tagged hits."""
    combined = []
    for site in sites_for(media_type):
        for item in search_site(site, title)[:8]:
            url = item.get("url")
            if not url:
                continue
            combined.append(
                {"title": item.get("title") or title, "url": url, "site": site}
            )
            if len(combined) >= 25:
                return combined
    return combined


MOVIE_LANGS = ["German Dub", "English Dub"]
SERIES_LANGS = ["German Dub", "English Dub", "English Sub", "German Sub"]

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


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _read_config():
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


# ---------------------------------------------------------------------------
# Enqueue helpers (run in an executor — they do blocking network + sqlite work)
# ---------------------------------------------------------------------------
def _enqueue(title, url, media_type, language, provider, requester, requester_id):
    if media_type == "movie":
        episodes = [url]
    else:
        prov = resolve_provider(url)
        series = prov.series_cls(url=url)
        episodes = []
        for season in series.seasons:
            for episode in season.episodes:
                episodes.append(episode.url)
        if not episodes:
            raise RuntimeError("no episodes found for series")

    add_to_queue(
        title=title,
        series_url=url,
        episodes=episodes,
        language=language,
        provider=provider,
        username=requester,
        source="discord",
        discord_user_id=requester_id,
    )


def _default_provider():
    provider = os.environ.get("ANIWORLD_PROVIDER", "VOE").strip()
    return provider or "VOE"


# ---------------------------------------------------------------------------
# Completion notification (called from the queue worker thread)
# ---------------------------------------------------------------------------
def notify_completed(title, media_type, language, discord_user_id):
    """DM the requester and (optionally) announce a finished download.

    Safe to call from any thread: it schedules the coroutine on the bot's own
    event loop and returns immediately. No-op when the bot isn't running.
    """
    with _lock:
        loop = _state.get("loop")
        client = _state.get("client")
        config = _state.get("config")
    if not (loop and client and getattr(loop, "is_running", lambda: False)()):
        return
    try:
        asyncio.run_coroutine_threadsafe(
            _announce_and_dm(client, config, title, media_type, language, discord_user_id),
            loop,
        )
    except Exception as exc:  # pragma: no cover
        logger.info("Discord: could not schedule completion notice: %s", exc)


async def _announce_and_dm(client, config, title, media_type, language, user_id):
    # Always DM the requester.
    if user_id:
        try:
            user = await client.fetch_user(int(user_id))
            await user.send(t(config, "available_dm", title=title))
        except Exception as exc:
            logger.info("Discord: could not DM requester on completion: %s", exc)

    # Optionally announce in a shared channel.
    channel_id = (config or {}).get("announce_channel_id")
    if not channel_id:
        return
    try:
        channel = client.get_channel(int(channel_id))
        if channel is None:
            channel = await client.fetch_channel(int(channel_id))
        type_key = "type_movie" if media_type == "movie" else "type_series"
        embed = discord.Embed(
            title=t(config, "available_title", title=title),
            description=t(config, "available_desc", title=title, language=language),
            color=0x22C55E,
        )
        embed.add_field(name=t(config, "f_type"), value=t(config, type_key), inline=True)
        embed.add_field(name=t(config, "f_language"), value=language, inline=True)
        await channel.send(embed=embed)
    except Exception as exc:
        logger.warning("Discord: announce to channel failed: %s", exc)


# ---------------------------------------------------------------------------
# Bot construction
# ---------------------------------------------------------------------------
def _build_client(config):
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    async def _search_all(title, media_type):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, aggregate_search, title, media_type)

    def _has_role(interaction):
        if not config["role_id"]:
            return True
        member = interaction.user
        roles = getattr(member, "roles", None)
        if not roles:
            return False
        return any(str(r.id) == config["role_id"] for r in roles)

    async def _owner_user():
        if not config["owner_id"]:
            return None
        try:
            return await client.fetch_user(int(config["owner_id"]))
        except Exception as exc:
            logger.warning("Discord: could not fetch owner: %s", exc)
            return None

    class LanguageSelect(discord.ui.Select):
        def __init__(self, ctx):
            self.ctx = ctx
            media_type = ctx["media_type"]
            langs = MOVIE_LANGS if media_type == "movie" else SERIES_LANGS
            options = [
                discord.SelectOption(
                    label=_lang_option_label(config, lang, media_type), value=lang
                )
                for lang in langs
            ]
            super().__init__(placeholder=t(config, "language_ph"), options=options)

        async def callback(self, interaction):
            self.ctx["language"] = self.values[0]
            await _finalize(interaction, self.ctx)

    class ResultSelect(discord.ui.Select):
        def __init__(self, ctx, results):
            self.ctx = ctx
            self.results = results[:25]
            options = []
            for idx, item in enumerate(self.results):
                title = (item.get("title") or "Unknown")[:80]
                site = SITE_LABELS.get(item.get("site", ""), item.get("site", ""))
                options.append(
                    discord.SelectOption(label=title, description=site, value=str(idx))
                )
            super().__init__(placeholder=t(config, "pick_title"), options=options)

        async def callback(self, interaction):
            chosen = self.results[int(self.values[0])]
            self.ctx["title"] = chosen.get("title") or self.ctx["title"]
            self.ctx["url"] = chosen["url"]
            self.ctx["site"] = chosen.get("site", "")
            view = discord.ui.View(timeout=300)
            view.add_item(LanguageSelect(self.ctx))
            await interaction.response.edit_message(
                content=t(config, "choose_language", title=self.ctx["title"]),
                view=view,
            )

    async def _finalize(interaction, ctx):
        ctx["provider"] = _default_provider()
        if config["mode"] == "advanced":
            await _do_enqueue(interaction, ctx)
        else:
            await _request_owner_approval(interaction, ctx)

    async def _do_enqueue(interaction, ctx):
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
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
            await _safe_edit(
                interaction, t(config, "queue_failed", title=ctx["title"], error=exc)
            )
            return
        await _safe_edit(
            interaction,
            t(config, "queued", title=ctx["title"], language=ctx["language"]),
        )

    async def _request_owner_approval(interaction, ctx):
        owner = await _owner_user()
        if owner is None:
            await _safe_edit(interaction, t(config, "no_owner"))
            return

        embed = discord.Embed(
            title=t(config, "req_title"),
            description=f"**{ctx['title']}**",
            color=0x2563EB,
        )
        type_key = "type_movie" if ctx["media_type"] == "movie" else "type_series"
        embed.add_field(name=t(config, "f_type"), value=t(config, type_key), inline=True)
        embed.add_field(name=t(config, "f_language"), value=ctx["language"], inline=True)
        embed.add_field(name=t(config, "f_site"), value=ctx["site"], inline=True)
        embed.add_field(
            name=t(config, "f_requested_by"), value=ctx["requester_name"], inline=False
        )
        embed.add_field(name=t(config, "f_url"), value=ctx["url"], inline=False)

        try:
            await owner.send(embed=embed, view=OwnerApprovalView(ctx))
        except Exception as exc:
            logger.error("Discord: could not DM owner: %s", exc)
            await _safe_edit(interaction, t(config, "owner_unreachable"))
            return

        await _safe_edit(
            interaction, t(config, "sent_for_approval", title=ctx["title"])
        )

    class OwnerApprovalView(discord.ui.View):
        def __init__(self, ctx):
            super().__init__(timeout=None)
            self.ctx = ctx

        @discord.ui.button(
            label=t(config, "btn_accept"), style=discord.ButtonStyle.success
        )
        async def accept(self, interaction, button):
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(
                    None,
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
                content=t(config, "accepted_owner", title=self.ctx["title"]),
                view=None,
            )
            await _dm_requester(
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
            reason = str(self.reason.value or "").strip()
            await interaction.response.edit_message(
                content=t(config, "declined_owner", title=self.ctx["title"]), view=None
            )
            msg = t(config, "declined_dm", title=self.ctx["title"])
            if reason:
                msg += "\n" + t(config, "declined_reason", reason=reason)
            await _dm_requester(self.ctx, msg)

    async def _dm_requester(ctx, message):
        try:
            user = await client.fetch_user(int(ctx["requester_id"]))
            await user.send(message)
        except Exception as exc:
            logger.info("Discord: could not DM requester: %s", exc)

    async def _safe_edit(interaction, content):
        try:
            await interaction.response.edit_message(content=content, view=None)
        except Exception:
            try:
                await interaction.edit_original_response(content=content, view=None)
            except Exception:
                pass

    async def _start_request(interaction, title, media_type):
        if not _has_role(interaction):
            await interaction.response.send_message(
                t(config, "no_permission"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            results = await _search_all(title, media_type)
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
        view = discord.ui.View(timeout=300)
        view.add_item(ResultSelect(ctx, results))
        await interaction.followup.send(
            content=t(config, "results_for", title=title), view=view, ephemeral=True
        )

    @tree.command(name=t(config, "cmd_movie"), description=t(config, "cmd_movie_desc"))
    @app_commands.describe(title=t(config, "arg_movie_title"))
    async def movie_request(interaction, title: str):
        await _start_request(interaction, title, "movie")

    @tree.command(name=t(config, "cmd_series"), description=t(config, "cmd_series_desc"))
    @app_commands.describe(title=t(config, "arg_series_title"))
    async def series_request(interaction, title: str):
        await _start_request(interaction, title, "series")

    @client.event
    async def on_ready():
        with _lock:
            _state["running"] = True
            _state["error"] = None
            _state["user"] = str(client.user)
        try:
            if config["guild_id"]:
                guild = discord.Object(id=int(config["guild_id"]))
                tree.copy_global_to(guild=guild)
                await tree.sync(guild=guild)
                # Drop any stale GLOBAL commands (e.g. left by a previous bot that
                # used this token) so only the guild commands remain.
                tree.clear_commands(guild=None)
                await tree.sync()
            else:
                await tree.sync()
        except Exception as exc:
            logger.warning("Discord: command sync failed: %s", exc)
        logger.info("Discord bot ready as %s", client.user)

    # Stash what the stop path needs to unregister the commands.
    client._aniworld_tree = tree
    client._aniworld_guild_id = config["guild_id"]
    return client


# ---------------------------------------------------------------------------
# Thread / lifecycle management
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
            _state["running"] = False
            _state["loop"] = None
            _state["client"] = None
            _state["user"] = None


async def _clear_commands(client):
    """Unregister the bot's slash commands from Discord (guild and global)."""
    tree = getattr(client, "_aniworld_tree", None)
    if tree is None:
        return
    guild_id = getattr(client, "_aniworld_guild_id", "")
    tree.clear_commands(guild=None)
    await tree.sync()
    if guild_id:
        guild = discord.Object(id=int(guild_id))
        tree.clear_commands(guild=guild)
        await tree.sync(guild=guild)


def _stop_locked():
    client = _state.get("client")
    loop = _state.get("loop")
    thread = _state.get("thread")
    if client and loop and loop.is_running():
        # Remove the registered slash commands first so nothing lingers on the
        # server while the bot is off, then close the connection.
        try:
            asyncio.run_coroutine_threadsafe(
                _clear_commands(client), loop
            ).result(timeout=20)
        except Exception as exc:
            logger.warning("Discord: clearing commands on stop failed: %s", exc)
        asyncio.run_coroutine_threadsafe(client.close(), loop)
    if thread and thread.is_alive():
        thread.join(timeout=10)
    _state["thread"] = None
    _state["running"] = False
    _state["config"] = None


def reconcile():
    """Start, stop or restart the bot to match the current configuration."""
    if not DISCORD_AVAILABLE:
        with _lock:
            _state["error"] = "discord.py not installed"
        return

    config = _read_config()
    with _lock:
        running = _state["thread"] is not None and _state["thread"].is_alive()
        prev = _state["config"]

        should_run = config["enabled"] and bool(config["token"])

        if not should_run:
            if running:
                _stop_locked()
            _state["error"] = None if config["enabled"] else None
            return

        # Restart when a relevant value changed
        if running and prev == config:
            return
        if running:
            _stop_locked()

        _state["config"] = config
        _state["error"] = None
        thread = threading.Thread(target=_run_bot, args=(config,), daemon=True)
        _state["thread"] = thread
        thread.start()


def start_if_enabled():
    """Called on web startup."""
    try:
        reconcile()
    except Exception as exc:
        logger.error("Discord bot start failed: %s", exc)
