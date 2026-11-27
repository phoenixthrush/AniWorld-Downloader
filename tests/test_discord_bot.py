"""The Discord bot lifecycle, driven with a stand-in client.

discord.py is optional, so `_build_client` is replaced by a fake whose start()
just waits until close() is called. Nothing ever talks to Discord.
"""

import _socket
import asyncio
import socket
import time
from threading import Event, Thread

import pytest

from aniworld.web import discord_bot


class FakeClient:
    def __init__(self):
        self.closed = asyncio.Event()

    async def start(self, token):
        await self.closed.wait()

    async def close(self):
        self.closed.set()


def wait_for(condition, timeout=5):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def loopback_only(sock, address):
    if address[0] not in ("127.0.0.1", "::1"):
        raise RuntimeError("a test tried to open a network connection")
    return _socket.socket.connect(sock, address)


@pytest.fixture
def bot(monkeypatch):
    # On Windows the event loop's self-pipe is a loopback socketpair
    monkeypatch.setattr(socket.socket, "connect", loopback_only)
    monkeypatch.setattr(discord_bot, "DISCORD_AVAILABLE", True)
    monkeypatch.setattr(discord_bot, "_build_client", lambda config: FakeClient())
    monkeypatch.setenv("ANIWORLD_DISCORD_BOT_ENABLED", "1")
    monkeypatch.setenv("ANIWORLD_DISCORD_TOKEN", "first")
    yield monkeypatch
    monkeypatch.setenv("ANIWORLD_DISCORD_BOT_ENABLED", "0")
    discord_bot.reconcile()


def test_a_restart_is_quick_and_keeps_the_new_bot(bot):
    state = discord_bot._state
    discord_bot.reconcile()
    wait_for(lambda: state["client"] is not None)
    old_client, old_thread = state["client"], state["thread"]

    bot.setenv("ANIWORLD_DISCORD_TOKEN", "second")
    started = time.monotonic()
    discord_bot.reconcile()
    assert time.monotonic() - started < 5
    assert not old_thread.is_alive()

    wait_for(lambda: state["client"] not in (None, old_client))
    assert state["loop"] is not None
    assert state["thread"].is_alive()


def test_stopping_clears_the_bot(bot):
    state = discord_bot._state
    discord_bot.reconcile()
    wait_for(lambda: state["client"] is not None)

    bot.setenv("ANIWORLD_DISCORD_BOT_ENABLED", "0")
    discord_bot.reconcile()
    assert state["thread"] is None
    assert state["client"] is None and state["loop"] is None


def test_disabling_the_bot_cancels_a_pending_start(bot):
    building = Event()
    finish_build = Event()
    logged_in = Event()

    class Client(FakeClient):
        async def start(self, token):
            logged_in.set()

    def build(config):
        building.set()
        assert finish_build.wait(5)
        return Client()

    bot.setattr(discord_bot, "_build_client", build)
    discord_bot.reconcile()
    assert building.wait(5)
    thread = discord_bot._state["thread"]
    bot.setenv("ANIWORLD_DISCORD_BOT_ENABLED", "0")
    stopping = Thread(target=discord_bot.reconcile)
    stopping.start()
    try:
        wait_for(lambda: discord_bot._state["thread"] is None)
    finally:
        finish_build.set()
        stopping.join(timeout=5)
        thread.join(timeout=5)

    assert not stopping.is_alive() and not thread.is_alive()
    assert not logged_in.is_set()
    assert discord_bot._state["client"] is None
