#!/usr/bin/env bash
# Install the nightly backup + integrity check as a systemd user timer.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.config/systemd/user
ln -sf "$here/kura-kira-nightly.service" ~/.config/systemd/user/
ln -sf "$here/kura-kira-nightly.timer" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now kura-kira-nightly.timer
systemctl --user list-timers kura-kira-nightly.timer --no-pager
