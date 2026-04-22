# CODE_INDEX — disclaude

On-demand Claude Discord session. Gateway bot always runs; Claude session spawns on first message and kills after idle timeout.

## Architecture (post 2026-04-22 refactor)

```
Discord → gateway.py (always-on bot) → tmux disclaude session (on-demand)
                                          ↳ claude --mcp-config mcp_config.json --strict-mcp-config
                                                    ↳ discord_mcp.py (Discord REST tools)
```

- **One** Discord WebSocket connection: gateway.py
- Claude session zero idle burn: spawns on message, kills after 10 min silence
- Discord reply/react/etc via REST (discord_mcp.py) — no WebSocket conflict

## gateway.py

| Lines | Symbol | Purpose |
|------:|--------|---------|
| 1–25  | constants | `STATE_DIR`, `TMUX_SESSION`, `IDLE_TIMEOUT` (600s), `SPAWN_WAIT` (20s), `INIT_SETTLE` (4s) |
| 27–42 | `_load_token()` | Reads `DISCORD_BOT_TOKEN` from env or `~/.claude/channels/discord/.env` |
| 44–49 | `load_access()` | Loads `~/.claude/channels/discord/access.json` (allowlist) |
| 51–68 | `is_allowed()` | Enforces DM policy + guild channel allowlist with optional requireMention |
| 70–74 | `tmux_session_exists()` | Checks if disclaude tmux session is alive |
| 76–90 | `spawn_claude()` | Kills stale session; spawns new tmux session running claude |
| 92–94 | `kill_claude()` | Kills disclaude tmux session |
| 97–125 | `inject_message()` | Formats `<channel>` tag; sends via two tmux send-keys calls (text, then Enter) |
| 128–186 | `GatewayBot` | discord.py Client subclass |
| 136–139 | `on_ready()` | Logs connect; starts idle watchdog task |
| 141–183 | `on_message()` | Allowlist check → queue during spawn → spawn → flush queue → inject |
| 185–193 | `_idle_watchdog()` | Checks every 60s; kills session after `IDLE_TIMEOUT` seconds of silence |

**Key behaviours:**
- Spawn lock (`_spawn_lock`) prevents concurrent spawns when messages arrive during init
- Queue (`_queue`) holds messages received during the `SPAWN_WAIT + INIT_SETTLE` window
- `inject_message` sends message text and Enter as separate `tmux send-keys` calls (combined call doesn't submit in claude's readline)

## discord_mcp.py

MCP stdio server. Provides Discord outbound tools via REST API only — no WebSocket, no bot token conflict with gateway.

| Lines | Symbol | Purpose |
|------:|--------|---------|
| 1–30  | imports + constants | `STATE_DIR`, `INBOX_DIR`, `DISCORD_API`, `MAX_CHUNK` (1900) |
| 32–44 | `_load_token()` | Same token source as gateway |
| 46–48 | `HEADERS` | Bot auth header for REST calls |
| 50–62 | `_chunk_text()` | Splits long messages at newline/space boundaries |
| 64–130 | `do_reply/react/edit/fetch/download` | Async REST implementations |
| 132–200 | `TOOLS` | MCP Tool definitions (reply, react, edit_message, fetch_messages, download_attachment) |
| 202–220 | `INSTRUCTIONS` | System prompt injected via MCP initialize — same text as old plugin:discord |
| 222 | `server` | `Server("discord-rest", instructions=INSTRUCTIONS)` |
| 224–231 | `list_tools` handler | Returns `TOOLS` |
| 233–258 | `call_tool` handler | Signature `(tool_name, arguments)` — matches mcp lib's calling convention |
| 260–270 | `main()` | Validates token; runs `stdio_server` |

**Important:** Handler signature must be `async def call_tool(tool_name: str, arguments: dict)` — the mcp library passes two positional args, not a request object.

## mcp_config.json

Tells claude to load `discord_mcp.py` as the "discord" MCP server. Key in `mcpServers` must be `"discord"` — this sets the permission prefix (`mcp__discord__*`).

## start.sh

Manual/emergency use only. Gateway manages the lifecycle in production. Flags: `--mcp-config mcp_config.json --strict-mcp-config` (no `--channels plugin:discord`).

## .claude/settings.json

Pre-approves `mcp__discord__*` tool calls so the session never stalls on permission prompts. Key entries: `mcp__discord__reply`, `mcp__discord__react`, `mcp__discord__edit_message`, `mcp__discord__fetch_messages`, `mcp__discord__download_attachment`.

## ~/.config/systemd/user/disclaude.service

`ExecStart` now runs `gateway.py` (not `start.sh`). `ExecStop` still kills the tmux session. Restart policy: `on-failure`, 10s cooldown.

## ~/.claude/channels/discord/

- `.env` — `DISCORD_BOT_TOKEN=...` (read by both gateway.py and discord_mcp.py)
- `access.json` — allowlist managed by `/discord:access` skill; gateway reads this on every message
- `inbox/` — attachment downloads land here (from `download_attachment` tool)

## What was removed

- `--channels plugin:discord@claude-plugins-official` flag — replaced by `--mcp-config` + `--strict-mcp-config`
- `plugin:discord` no longer loaded in disclaude sessions (`--strict-mcp-config` blocks it)
- Always-on claude session — idle burn eliminated
