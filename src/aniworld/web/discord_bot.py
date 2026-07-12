"""Optional Discord request bot.

Users request a movie or series from Discord. The bot searches the actual
streaming site and shows the real hits in a dropdown, so the requester picks
the exact title — this is why it can never grab "the wrong movie" the way a
blind first-hit matcher would. Depending on the configured mode the request is
either sent to the owner for approval (standard) or queued straight away
(advanced).

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
def _enqueue(title, url, media_type, language, provider, requester):
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
    )


def _default_provider():
    provider = os.environ.get("ANIWORLD_PROVIDER", "VOE").strip()
    return provider or "VOE"


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
            langs = MOVIE_LANGS if ctx["media_type"] == "movie" else SERIES_LANGS
            options = [discord.SelectOption(label=lang) for lang in langs]
            super().__init__(placeholder="Language", options=options)

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
            super().__init__(placeholder="Pick the exact title", options=options)

        async def callback(self, interaction):
            chosen = self.results[int(self.values[0])]
            self.ctx["title"] = chosen.get("title") or self.ctx["title"]
            self.ctx["url"] = chosen["url"]
            self.ctx["site"] = chosen.get("site", "")
            view = discord.ui.View(timeout=300)
            view.add_item(LanguageSelect(self.ctx))
            await interaction.response.edit_message(
                content=f"**{self.ctx['title']}** — choose a language:", view=view
            )

    async def _finalize(interaction, ctx):
        ctx["provider"] = _default_provider()
        if config["mode"] == "advanced":
            await _do_enqueue(interaction, ctx, notify_owner=False)
        else:
            await _request_owner_approval(interaction, ctx)

    async def _do_enqueue(interaction, ctx, notify_owner):
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
            )
        except Exception as exc:
            logger.error("Discord enqueue failed: %s", exc)
            await _safe_edit(
                interaction, f"❌ Could not queue **{ctx['title']}**: {exc}"
            )
            return
        await _safe_edit(
            interaction,
            f"✅ **{ctx['title']}** ({ctx['language']}) was added to the download queue.",
        )

    async def _request_owner_approval(interaction, ctx):
        owner = await _owner_user()
        if owner is None:
            await _safe_edit(
                interaction,
                "⚠️ No owner is configured, so the request can't be forwarded.",
            )
            return

        embed = discord.Embed(
            title="New download request",
            description=f"**{ctx['title']}**",
            color=0x2563EB,
        )
        embed.add_field(name="Type", value=ctx["media_type"], inline=True)
        embed.add_field(name="Language", value=ctx["language"], inline=True)
        embed.add_field(name="Site", value=ctx["site"], inline=True)
        embed.add_field(name="Requested by", value=ctx["requester_name"], inline=False)
        embed.add_field(name="URL", value=ctx["url"], inline=False)

        try:
            await owner.send(embed=embed, view=OwnerApprovalView(ctx))
        except Exception as exc:
            logger.error("Discord: could not DM owner: %s", exc)
            await _safe_edit(interaction, "⚠️ Could not reach the owner via DM.")
            return

        await _safe_edit(
            interaction,
            f"📨 Your request for **{ctx['title']}** was sent for approval.",
        )

    class OwnerApprovalView(discord.ui.View):
        def __init__(self, ctx):
            super().__init__(timeout=None)
            self.ctx = ctx

        @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
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
                )
            except Exception as exc:
                await interaction.response.edit_message(
                    content=f"❌ Failed to queue: {exc}", view=None
                )
                return
            await interaction.response.edit_message(
                content=f"✅ Accepted — **{self.ctx['title']}** is downloading.",
                view=None,
            )
            await _dm_requester(
                self.ctx,
                f"✅ Your request **{self.ctx['title']}** was accepted and is downloading.",
            )

        @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
        async def decline(self, interaction, button):
            await interaction.response.send_modal(DeclineModal(self.ctx))

    class DeclineModal(discord.ui.Modal, title="Decline request"):
        def __init__(self, ctx):
            super().__init__()
            self.ctx = ctx
            self.reason = discord.ui.TextInput(
                label="Reason (optional)",
                required=False,
                style=discord.TextStyle.paragraph,
            )
            self.add_item(self.reason)

        async def on_submit(self, interaction):
            reason = str(self.reason.value or "").strip()
            await interaction.response.edit_message(
                content=f"🚫 Declined **{self.ctx['title']}**.", view=None
            )
            msg = f"🚫 Your request **{self.ctx['title']}** was declined."
            if reason:
                msg += f"\nReason: {reason}"
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
                "You don't have permission to request.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            # Search every site of this type and combine the hits.
            results = await _search_all(title, media_type)
        except Exception as exc:
            await interaction.followup.send(f"Search failed: {exc}", ephemeral=True)
            return
        if not results:
            await interaction.followup.send(
                f"No results found for **{title}**.", ephemeral=True
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
            content=f"Results for **{title}**:", view=view, ephemeral=True
        )

    @tree.command(name="film-anfrage", description="Request a movie")
    @app_commands.describe(title="Movie title")
    async def film_anfrage(interaction, title: str):
        await _start_request(interaction, title, "movie")

    @tree.command(name="serien-anfrage", description="Request a series")
    @app_commands.describe(title="Series title")
    async def serien_anfrage(interaction, title: str):
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
            else:
                await tree.sync()
        except Exception as exc:
            logger.warning("Discord: command sync failed: %s", exc)
        logger.info("Discord bot ready as %s", client.user)

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


def _stop_locked():
    client = _state.get("client")
    loop = _state.get("loop")
    thread = _state.get("thread")
    if client and loop and loop.is_running():
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
