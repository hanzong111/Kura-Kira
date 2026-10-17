#!/usr/bin/env bash
# Install the dashboard as a systemd user service: starts at login, restarts on failure.
#   dashboard/install-service.sh            # serve the real ledger ~/duit/data/duit.db
#   DUIT_DB=/path/to.db dashboard/install-service.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(dirname "$here")"
unit=kura-kira-dashboard.service
units="$HOME/.config/systemd/user"
db="${DUIT_DB:-$HOME/duit/data/duit.db}"
cfg="${DUIT_CONFIG:-$HOME/duit/config.toml}"

mkdir -p "$units/$unit.d"
ln -sf "$here/$unit" "$units/$unit"
{
  echo "[Service]"
  echo "WorkingDirectory=$repo"
  echo "Environment=DUIT_DB=$db"
  # the bot's config.toml; without one the server falls back to config.example.toml
  if [ -f "$cfg" ]; then echo "Environment=DUIT_CONFIG=$cfg"; fi
} > "$units/$unit.d/local.conf"

systemctl --user daemon-reload
systemctl --user enable --now "$unit"
systemctl --user restart "$unit"
echo "installed $unit from $repo (ledger $db) -> http://localhost:8790"
