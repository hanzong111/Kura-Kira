#!/usr/bin/env bash
# Run the tests in the project venv, isolated from system pytest plugins (e.g. ROS on PYTHONPATH).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"; }
env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest "$@"
