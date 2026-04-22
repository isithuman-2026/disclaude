# disclaude

On-demand Claude Code Discord bot. A lightweight gateway process watches Discord 24/7; a Claude Code session spawns only when a message arrives and shuts down after ten minutes of silence.

No idle rate-limit burn. No GPU. No local model.

## Why this exists

Running Claude Code as a Discord bot the naive way — a persistent tmux session managed by systemd — works fine until you check your weekly rate limit after a quiet weekend. Claude's active sessions consume budget through cache refreshes and context keepalives whether or not anyone is talking to the bot. Two quiet days cost most of a weekly budget doing nothing useful.

The fix: Claude only runs when there is work to do.

## Architecture

```
Discord ──► gateway.py (always-on, ~32MB RAM) ──► tmux session (on-demand)
                                                        └─ claude --mcp-config mcp_config.json
                                                                   └─ discord_mcp.py (REST tools)
```

`gateway.py` is a minimal discord.py bot. It holds the Discord WebSocket connection permanently, enforces an allowlist, and manages the Claude session lifecycle. It makes no API calls while Discord is quiet.

`discord_mcp.py` is a stdio MCP server that gives Claude outbound Discord tools: `reply`, `react`, `edit_message`, `fetch_messages`, `download_attachment`. All calls go via REST, not WebSocket, so there is no token conflict with the gateway.

## Why this instead of a local LLM stack

If your homelab machine has a low-spec or no dedicated GPU, running local LLM inference is not practical. A local stack needs VRAM, model downloads, inference overhead, and a service layer just to approximate what Claude does natively. The operational surface is large and the model quality ceiling is lower.

disclaude skips all of that. You get full Claude Code capabilities (tool use, MCP, file access, shell, the whole Claude Code feature set) on a machine with no GPU, no VRAM, and as little as a few hundred MB of free RAM. The gateway itself sits at around 32MB. The only compute requirements are on Anthropic's side.

The tradeoff is that you pay per session via a Claude Pro, Max, or API subscription rather than running inference yourself. For personal homelab use where the bot is idle most of the day, the on-demand model makes this cost negligible.

## Advantages

- **Zero idle cost.** No Claude session, no API calls, no rate-limit burn during quiet periods.
- **No GPU or local inference.** Runs on any machine that can run Python and the Claude Code CLI.
- **Full Claude Code.** Not a stripped-down API wrapper. You get tools, MCP servers, file access, shell execution, memory, and everything else Claude Code supports.
- **Access control.** Per-channel allowlist with optional mention-gating. Managed via `~/.claude/channels/discord/access.json`.
- **Single process to monitor.** The gateway is the only long-lived process. Claude's lifecycle is fully managed.
- **Fast enough for async conversation.** Cold-start (first message after idle) is around 12 seconds. Subsequent messages in the same session are immediate.

## Limitations

- **Requires a Claude subscription or API key.** Claude Pro, Max, or Anthropic API access. This is not a free setup.
- **Single concurrent session.** One Claude instance per gateway. Overlapping conversations from different users are handled sequentially, not in parallel.
- **12-second cold start.** First message after the session has been idle triggers a spawn. There is no way to pre-warm without re-introducing idle burn.
- **Host must be running 24/7.** The gateway process needs to stay alive to receive messages. Suitable for a home server, VPS, or always-on machine; not suitable for a laptop or desktop that sleeps.
- **tmux dependency.** Claude is launched inside a tmux session. tmux must be installed on the host.
- **No conversation history across sessions.** When Claude's session is killed after idle timeout, context is lost. The next session starts fresh.

## Requirements

- Python 3.12+
- Claude Code CLI installed and authenticated (`~/.claude/`)
- tmux
- A Discord bot token with the **Message Content Intent** enabled
- A Discord server where you have permission to add a bot

## Setup

```bash
# Clone and create virtualenv
git clone https://github.com/isithuman-2026/disclaude.git
cd disclaude
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Generate mcp_config.json with correct absolute paths for this machine
./setup.sh

# Store your bot token
mkdir -p ~/.claude/channels/discord
echo "DISCORD_BOT_TOKEN=your_token_here" > ~/.claude/channels/discord/.env

# Create an allowlist (see Access Control below)
echo '{"policy": "allowlist", "channels": []}' > ~/.claude/channels/discord/access.json
```

### Run manually

```bash
.venv/bin/python gateway.py
```

### Run as a systemd user service

Create `~/.config/systemd/user/disclaude.service`:

```ini
[Unit]
Description=disclaude — on-demand Claude gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/path/to/disclaude
ExecStart=/path/to/disclaude/.venv/bin/python /path/to/disclaude/gateway.py
ExecStop=/usr/bin/tmux kill-session -t disclaude
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now disclaude
```

## Access Control

The gateway reads `~/.claude/channels/discord/access.json` on every message. Format:

```json
{
  "policy": "allowlist",
  "channels": ["123456789012345678"],
  "requireMention": false,
  "allowDMs": false
}
```

`channels` is a list of Discord channel IDs (right-click a channel, Copy Channel ID). The bot ignores messages from channels not in the list.

## Customising Claude's behaviour

`CLAUDE.md` in the project root is loaded by Claude Code at session start. Edit it to set context, constraints, and instructions specific to your setup. The version in this repo is a minimal starting point.

`.claude/settings.json` pre-approves the five Discord MCP tools so Claude never stalls on permission prompts. Add Bash or other tool permissions here to match your use case.

## How it handles the dual-WebSocket problem

A Discord bot token supports one active WebSocket connection. If you run Claude Code with `plugin:discord` while the gateway is also connected, the plugin opens a second connection with the same token and drops the gateway offline.

disclaude avoids this by not loading `plugin:discord` at all. The gateway owns the WebSocket. Claude gets outbound Discord tools via `discord_mcp.py`, which uses REST only. The `--strict-mcp-config` flag prevents Claude from loading any globally-enabled plugins.

## Related

Blog post with architecture detail and the three things that silently broke during development: [buildtestrun.com/disclaude-on-demand-claude-discord-bot](https://buildtestrun.com/disclaude-on-demand-claude-discord-bot)
