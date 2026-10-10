#!/bin/bash
# Build and audit the August discovery supplement 2026-07-25..2026-08-28 (end exclusive).
# Starts at the holdout end (2026-07-25T00Z, exclusive) and stops before the quarantined day 2026-08-28.
# 2026-09-21 onward stays unbuilt: reserved as fresh out-of-sample.
cd "$(git rev-parse --show-toplevel)"
mkdir -p outputs/logs
LOG=outputs/logs/T09-build-august.log
exec > >(tee -a "$LOG") 2>&1
log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*"; }
START=2026-07-25
END=2026-08-28
SPLIT=discovery_supplemental_20260725_20260828

build_and_audit() {
  local inst=$1 slug=$2
  log "BUILD START $inst $START -> $END ($SPLIT)"
  uv run python -m evolution build-supplemental-discovery \
      --instrument-id "$inst" --start "$START" --end "$END" \
      --output-root data/evolution-data-supplemental || { log "BUILD FAILED $inst"; return 1; }
  log "AUDIT START $inst"
  uv run python -m evolution audit-supplemental-discovery \
      --instrument-id "$inst" --split "$SPLIT" --start "$START" --end "$END" \
      --dataset-root data/evolution-data-supplemental \
      --output "outputs/evolution-diagnostics/supplemental-audit-$SPLIT-$slug.json" || { log "AUDIT FAILED $inst"; return 1; }
  log "OK $inst"
}

build_and_audit BTCUSDT.BINANCE btcusdt
build_and_audit ETHUSDT.BINANCE ethusdt
build_and_audit BNBUSDT.BINANCE bnbusdt
log "ALL STEPS DONE"
