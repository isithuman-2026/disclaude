#!/usr/bin/env python3
"""
Disclaude gateway: always-on Discord bot that manages on-demand Claude Code sessions.

Receives Discord messages, enforces allowlist, spawns/kills the disclaude tmux
session as needed, and injects messages to Claude via tmux send-keys.
"""
import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import discord

STATE_DIR = Path.home() / ".claude" / "channels" / "discord"
ACCESS_FILE = STATE_DIR / "access.json"
ENV_FILE = STATE_DIR / ".env"
DISCLAUDE_DIR = Path.home() / "projects" / "disclaude"
TMUX_SESSION = "disclaude"
IDLE_TIMEOUT = 600   # seconds of silence before killing the claude session
SPAWN_WAIT = 20      # max seconds to wait for claude to initialise after spawn
INIT_SETTLE = 4      # extra seconds after tmux session appears before injecting


def _load_token() -> str:
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if token:
        return token
    try:
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("DISCORD_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def load_access() -> dict:
    try:
        return json.loads(ACCESS_FILE.read_text())
    except Exception:
        return {"dmPolicy": "pairing", "allowFrom": [], "groups": {}, "pending": {}}


def is_allowed(msg: discord.Message, access: dict) -> bool:
    sender_id = str(msg.author.id)

    if msg.guild is None:
        # DM
        policy = access.get("dmPolicy", "pairing")
        if policy == "disabled":
            return False
        return sender_id in access.get("allowFrom", [])

    # Guild channel
    channel_id = str(msg.channel.id)
    group_policies = access.get("groups", {})
    policy = group_policies.get(channel_id)
    if policy is None:
        return False
    if policy.get("requireMention"):
        me = msg.guild.me
        bot_id = str(me.id) if me else ""
        if not any(str(u.id) == bot_id for u in msg.mentions):
            return False
    return sender_id in policy.get("allowFrom", [])


def tmux_session_exists() -> bool:
    r = subprocess.run(["tmux", "has-session", "-t", TMUX_SESSION], capture_output=True)
    return r.returncode == 0


def spawn_claude() -> None:
    subprocess.run(["tmux", "kill-session", "-t", TMUX_SESSION], capture_output=True)
    claude_bin = Path.home() / ".local" / "bin" / "claude"
    mcp_config = DISCLAUDE_DIR / "mcp_config.json"
    cmd = [
        "tmux", "new-session", "-d", "-s", TMUX_SESSION, "-x", "220", "-y", "50",
        str(claude_bin),
        "--model", "claude-opus-4-7",
        "--permission-mode", "auto",
        "--effort", "low",
        "--mcp-config", str(mcp_config),
        "--strict-mcp-config",
    ]
    subprocess.run(cmd, env={**os.environ, "HOME": str(Path.home())})


def kill_claude() -> None:
    subprocess.run(["tmux", "kill-session", "-t", TMUX_SESSION], capture_output=True)


def inject_message(msg: discord.Message) -> None:
    ts = msg.created_at.isoformat()
    chat_id = str(msg.channel.id)
    message_id = str(msg.id)
    user = msg.author.name
    content = msg.content or "(attachment)"

    # Escape content for shell safety: single-quote the whole tag
    atts = []
    for att in msg.attachments:
        kb = att.size // 1024
        atts.append(f"{att.filename} ({att.content_type or 'unknown'}, {kb}KB)")

    att_attrs = ""
    if atts:
        count = len(atts)
        listing = "; ".join(atts)
        att_attrs = f' attachment_count="{count}" attachments="{listing}"'

    channel_tag = (
        f'<channel source="discord" chat_id="{chat_id}" message_id="{message_id}" '
        f'user="{user}" ts="{ts}"{att_attrs}>{content}</channel>'
    )

    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, channel_tag])
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "Enter"])


class GatewayBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        # DMs need the Partials.Channel trick from discord.py
        super().__init__(intents=intents)
        self.last_message_time: float = 0.0
        self._spawning = False
        self._spawn_lock = asyncio.Lock()
        self._queue: list[discord.Message] = []

    async def on_ready(self) -> None:
        print(f"[gateway] connected as {self.user}", flush=True)
        self.loop.create_task(self._idle_watchdog())

    async def on_message(self, msg: discord.Message) -> None:
        if msg.author.bot:
            return

        access = load_access()
        if not is_allowed(msg, access):
            return

        self.last_message_time = time.monotonic()

        async with self._spawn_lock:
            if self._spawning:
                # Already spawning; queue and return (lock released when done)
                self._queue.append(msg)
                return

            if not tmux_session_exists():
                self._spawning = True
                self._queue.append(msg)

        if self._spawning:
            print("[gateway] spawning claude session…", flush=True)
            await self.loop.run_in_executor(None, spawn_claude)

            # Wait for tmux session to appear
            for _ in range(SPAWN_WAIT):
                await asyncio.sleep(1)
                if tmux_session_exists():
                    break
            else:
                print("[gateway] WARNING: tmux session did not appear after spawn", flush=True)

            await asyncio.sleep(INIT_SETTLE)

            async with self._spawn_lock:
                self._spawning = False
                queued = list(self._queue)
                self._queue.clear()

            print(f"[gateway] session ready; injecting {len(queued)} queued message(s)", flush=True)
            for queued_msg in queued:
                inject_message(queued_msg)
        else:
            inject_message(msg)

    async def _idle_watchdog(self) -> None:
        while True:
            await asyncio.sleep(60)
            if not tmux_session_exists():
                continue
            if self.last_message_time == 0.0:
                continue
            idle = time.monotonic() - self.last_message_time
            if idle > IDLE_TIMEOUT:
                print(f"[gateway] idle {idle:.0f}s — killing claude session", flush=True)
                await self.loop.run_in_executor(None, kill_claude)
                self.last_message_time = 0.0


if __name__ == "__main__":
    TOKEN = _load_token()
    if not TOKEN:
        print("[gateway] ERROR: DISCORD_BOT_TOKEN not found in env or .env file", flush=True)
        raise SystemExit(1)
    bot = GatewayBot()
    bot.run(TOKEN)
