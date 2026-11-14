#!/usr/bin/env bash
# One-line bootstrap for the PGClockBot S-UI fork.
set -euo pipefail

REPO_URL="${PGCLOCK_REPO:-https://github.com/alirezasj7/PGClockBot-SUI.git}"
RAW_BASE="https://raw.githubusercontent.com/alirezasj7/PGClockBot-SUI/main"

if [[ -f "./pgclock.sh" && -f "./get.sh" ]]; then
  exec env \
    PGCLOCK_REPO="$REPO_URL" \
    PANEL_BACKEND="sui" \
    PGCLOCK_WEB_PORT="${PGCLOCK_WEB_PORT:-9000}" \
    PGCLOCK_SSL_MODE="${PGCLOCK_SSL_MODE:-none}" \
    bash ./pgclock.sh install-main "$@"
fi

command -v curl >/dev/null 2>&1 || {
  echo "curl is required. Install it with: sudo apt-get update && sudo apt-get install -y curl" >&2
  exit 1
}

exec env \
  PGCLOCK_REPO="$REPO_URL" \
  PGCLOCK_DIR="${PGCLOCK_DIR:-PGClockBot-SUI}" \
  PGCLOCK_CHANNEL="main" \
  PANEL_BACKEND="sui" \
  PGCLOCK_WEB_PORT="${PGCLOCK_WEB_PORT:-9000}" \
  PGCLOCK_SSL_MODE="${PGCLOCK_SSL_MODE:-none}" \
  bash <(curl -fsSL "${RAW_BASE}/get.sh") install-main "$@"
