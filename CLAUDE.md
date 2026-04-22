# CLAUDE.md — disclaude

On-demand Discord bot session. Session spawned by `gateway.py` when a Discord message arrives; idle 10 min = auto-shutdown. Messages arrive as `<channel source="discord" ...>` tags injected by the gateway via tmux send-keys. Discord tools (reply/react/etc) provided by `discord_mcp.py` via REST. All user-visible output MUST go through the Discord reply tool — no human watches the terminal.

## Context management

Session runs indefinitely. Compact proactively when context is heavy (many tool calls, long threads, before starting a new task). Confirm in Discord after compacting.

## Destructive actions

Pause and confirm via Discord before irreversible ops (rm, git push, service stop, container destroy, etc.).

## Discord slash commands

Messages starting with `/` are slash commands — invoke matching skill via the Skill tool. If no skill matches, explain the limitation. `/clear` is harness-level (not invokable) — offer `/compact` instead.

## Limits

No GUI, no browser. Do not push to git or send external messages without explicit user ask. Never expose credentials, internal IPs, or PII in Discord replies.

## Boot behaviour

Silent on session start. On first message after boot, brief ack confirming live.
