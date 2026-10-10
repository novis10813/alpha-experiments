#!/bin/bash
# Build supplemental executable discovery splits + audits (2026-09-21)
cd "$(git rev-parse --show-toplevel)"
mkdir -p outputs/logs
LOG=outputs/logs/build-supplemental-20260921.log
exec > >(tee -a "$LOG") 2>&1
log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*"; }

build_and_audit() {
  local inst=$1 start=$2 end=$3 split=$4 slug=$5
  log "BUILD START $inst $start -> $end ($split)"
  if uv run python -m evolution build-supplemental-discovery \
      --instrument-id "$inst" --start "$start" --end "$end" \
      --output-root data/evolution-data-supplemental; then
    log "BUILD OK $inst $split"
  else
    log "BUILD FAILED $inst $split (partial dir at data/evolution-data-supplemental/$split/$inst may need manual removal before retry)"
    return 1
  fi
  log "AUDIT START $inst $split"
  if uv run python -m evolution audit-supplemental-discovery \
      --instrument-id "$inst" --split "$split" --start "$start" --end "$end" \
      --dataset-root data/evolution-data-supplemental \
      --output "outputs/evolution-diagnostics/supplemental-audit-$split-$slug.json"; then
    log "AUDIT OK $inst $split"
  else
    log "AUDIT FAILED $inst $split"
    return 1
  fi
}

build_and_audit BTCUSDT.BINANCE 2026-09-05 2026-09-21 discovery_supplemental_20260905_20260921 btcusdt
build_and_audit ETHUSDT.BINANCE 2026-08-29 2026-09-21 discovery_supplemental_20260829_20260921 ethusdt
build_and_audit BNBUSDT.BINANCE 2026-08-29 2026-09-21 discovery_supplemental_20260829_20260921 bnbusdt
log "ALL STEPS DONE"
