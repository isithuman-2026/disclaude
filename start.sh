#!/usr/bin/env bash
set -euo pipefail

SESSION=disclaude
CLAUDE_BIN="${HOME}/.local/bin/claude"
IDLE_THRESHOLD=1800  # 30 minutes in seconds

cleanup() {
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    exit 0
}
trap cleanup TERM INT

idle_watchdog() {
    local last_compact=0
    local stats="$HOME/.claude/session-stats.json"
    while tmux has-session -t "$SESSION" 2>/dev/null; do
        sleep 60
        LAST_ACTIVITY=$(tmux display-message -t "$SESSION" -p '#{session_activity}' 2>/dev/null || echo 0)
        NOW=$(date +%s)
        IDLE=$((NOW - LAST_ACTIVITY))
        COOLDOWN_OK=$([ "$((NOW - last_compact))" -ge "$IDLE_THRESHOLD" ] && echo 1 || echo 0)
        # Idle-based compact
        if [ "$IDLE" -ge "$IDLE_THRESHOLD" ] && [ "$COOLDOWN_OK" = "1" ]; then
            tmux send-keys -t "$SESSION" '/compact' Enter
            last_compact=$NOW
            continue
        fi
        # Context-threshold compact: >=70% used and idle >=60s (don't interrupt active work)
        if [ -f "$stats" ] && [ "$IDLE" -ge 60 ] && [ "$COOLDOWN_OK" = "1" ]; then
            PCT=$(python3 -c "import json; print(int(json.load(open('$stats'))['context']['usagePct']))" 2>/dev/null || echo 0)
            if [ "$PCT" -ge 70 ]; then
                tmux send-keys -t "$SESSION" '/compact' Enter
                last_compact=$NOW
            fi
        fi
    done
}

while true; do
    # Kill stale session if present
    tmux kill-session -t "$SESSION" 2>/dev/null || true

    # Create session; claude runs as the session command so it owns the pty
    tmux new-session -d -s "$SESSION" -x 220 -y 50 \
        "$CLAUDE_BIN" --model claude-opus-4-7 --permission-mode auto --effort low \
        --mcp-config "${HOME}/projects/disclaude/mcp_config.json" \
        --strict-mcp-config

    # Start idle watchdog in background
    idle_watchdog &
    WATCHDOG_PID=$!

    # Block until the tmux session exits (claude died or was stopped)
    while tmux has-session -t "$SESSION" 2>/dev/null; do
        sleep 5
    done

    kill "$WATCHDOG_PID" 2>/dev/null || true

    echo "[disclaude] session ended, restarting in 5s..." >&2
    sleep 5
done
