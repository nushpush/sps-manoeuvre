#!/bin/bash
# Daily SPS announcement check — run by launchd at 09:00.
# Reads credentials from .bob/mcp.json so there's a single source of truth.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$PROJECT_DIR/.bob/daily-run.log"
MCP_JSON="$PROJECT_DIR/.bob/mcp.json"
SRC_DIR="$PROJECT_DIR/src"

# Find python3 — prefer pyenv shim if available, fall back to system python3
PYTHON="$(command -v python3)"
if [[ -z "$PYTHON" ]]; then
    echo "ERROR: python3 not found in PATH" >> "$LOG_FILE"
    exit 1
fi

# Rotate log: keep last 500 lines
if [[ -f "$LOG_FILE" ]]; then
    tail -500 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_FILE"

# Extract and export env vars from .bob/mcp.json
while IFS= read -r line; do
    export "$line"
done < <("$PYTHON" -c "
import json, sys
with open('$MCP_JSON') as f:
    env = json.load(f)['mcpServers']['sps-pipeline-bot']['env']
for k, v in env.items():
    print(f'{k}={v}')
")

cd "$SRC_DIR"
"$PYTHON" -m sps_pipeline_bot --run >> "$LOG_FILE" 2>&1
echo "--- exit $? ---" >> "$LOG_FILE"
