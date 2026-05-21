#!/bin/sh
set -eu

MOOTDX_CONFIG_PATH="${MOOTDX_CONFIG_PATH:-/root/.mootdx/config.json}"
MOOTDX_CONFIG_DIR="$(dirname "$MOOTDX_CONFIG_PATH")"
mkdir -p "$MOOTDX_CONFIG_DIR"

if [ "${KLINE_PROVIDER:-}" != "fake" ] && { [ ! -s "$MOOTDX_CONFIG_PATH" ] || [ "${KLINE_MOOTDX_REFRESH_ON_START:-}" = "true" ]; }; then
    echo "Preparing mootdx server config at $MOOTDX_CONFIG_PATH"
    python -m mootdx bestip || echo "Warning: mootdx bestip failed; continuing startup"
fi

exec "$@"
