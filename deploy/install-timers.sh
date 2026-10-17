#!/usr/bin/env bash
# Install every Kura-Kira systemd user timer in this folder (nightly check/backup + scheduled messages).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.config/systemd/user
for unit in "$here"/kura-kira-*.service "$here"/kura-kira-*.timer; do
  ln -sf "$unit" ~/.config/systemd/user/
done
systemctl --user daemon-reload
for t in "$here"/kura-kira-*.timer; do
  systemctl --user enable --now "$(basename "$t")"
done
systemctl --user list-timers 'kura-kira-*' --no-pager
