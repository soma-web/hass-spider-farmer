#!/usr/bin/env bash
# Run a development Home Assistant in WSL2 with this repo's integration linked in.
#
#   wsl -e bash /mnt/k/Projects/spider-farmer-hass/scripts/ha-dev.sh
#
# Then open http://localhost:8123 in Windows. Setup (once): uv + Python 3.14 +
# `uv pip install homeassistant==<version>` into ~/ha-dev/.venv (see Plan.md, M0).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HA_DIR="${HA_DIR:-$HOME/ha-dev}"
CONFIG="$HA_DIR/config"

mkdir -p "$CONFIG/custom_components"
ln -sfn "$REPO/custom_components/spider_farmer" "$CONFIG/custom_components/spider_farmer"

if [ ! -f "$CONFIG/configuration.yaml" ]; then
  cat > "$CONFIG/configuration.yaml" <<'EOF'
# default_config minus voice/cloud/mobile_app (pymicro-vad needs a compiler)
frontend:
config:
history:
logbook:
recorder:
energy:
system_health:

logger:
  default: info
  logs:
    custom_components.spider_farmer: debug
EOF
fi

exec "$HA_DIR/.venv/bin/hass" -c "$CONFIG" "$@"
