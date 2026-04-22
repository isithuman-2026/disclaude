#!/usr/bin/env bash
# Writes mcp_config.json with the correct absolute path for this install.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "ERROR: .venv not found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

cat > "${SCRIPT_DIR}/mcp_config.json" <<EOF
{
  "mcpServers": {
    "discord": {
      "command": "${PYTHON}",
      "args": ["${SCRIPT_DIR}/discord_mcp.py"],
      "env": {}
    }
  }
}
EOF

echo "Wrote mcp_config.json"
