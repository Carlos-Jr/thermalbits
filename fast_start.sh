#!/usr/bin/env bash
# fast_start.sh — One-shot setup for ThermalBits.
#
# Installs Python dependencies and builds both bundled Rust binaries
# (iron_circuit_sim for update_entropy and eo_do_rs for apply).
#
# Usage:
#   ./fast_start.sh            # runtime deps + release builds
#   ./fast_start.sh --dev      # also install development deps (pytest, ruff, ...)
#   ./fast_start.sh --docs     # also install documentation deps (mkdocs, ...)
#   ./fast_start.sh --no-native # skip -C target-cpu=native (portable builds)
#   ./fast_start.sh --help
#
# The flags can be combined, for example: ./fast_start.sh --dev --docs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

INSTALL_DEV=0
INSTALL_DOCS=0
USE_NATIVE=1
PY_BIN="${PYTHON:-python3}"

print_usage() {
    sed -n '2,15p' "$0"
}

for arg in "$@"; do
    case "$arg" in
        --dev) INSTALL_DEV=1 ;;
        --docs) INSTALL_DOCS=1 ;;
        --no-native) USE_NATIVE=0 ;;
        -h|--help) print_usage; exit 0 ;;
        *)
            echo "Unknown argument: $arg" >&2
            print_usage
            exit 2
            ;;
    esac
done

log() { printf '\033[1;34m[fast_start]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[fast_start]\033[0m %s\n' "$*" >&2; }

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        err "Required command not found in PATH: $1"
        exit 1
    fi
}

require_cmd "$PY_BIN"
require_cmd cargo

log "Using Python: $($PY_BIN --version 2>&1)"
log "Using cargo:  $(cargo --version)"

if [[ $INSTALL_DEV -eq 1 ]]; then
    log "Installing Python development dependencies"
    "$PY_BIN" -m pip install --upgrade pip
    "$PY_BIN" -m pip install -r requirements-dev.txt
else
    log "Installing Python runtime dependencies"
    "$PY_BIN" -m pip install --upgrade pip
    "$PY_BIN" -m pip install -r requirements.txt
fi

if [[ $INSTALL_DOCS -eq 1 ]]; then
    log "Installing documentation dependencies"
    "$PY_BIN" -m pip install -r documentation/requirements-docs.txt
fi

if [[ $USE_NATIVE -eq 1 ]]; then
    export RUSTFLAGS="${RUSTFLAGS:-}${RUSTFLAGS:+ }-C target-cpu=native"
    log "Using RUSTFLAGS=$RUSTFLAGS"
else
    log "Building portable binaries (no -C target-cpu=native)"
fi

log "Building iron_circuit_sim (entropy simulator) in release mode"
( cd thermalbits/iron_circuit_sim && cargo build --release )

log "Building eo_do_rs (parallel EO/DO transformer) in release mode"
( cd thermalbits/eo_do_rs && cargo build --release )

SIM_BIN="thermalbits/iron_circuit_sim/target/release/circuit_sim"
EODO_BIN="thermalbits/eo_do_rs/target/release/eo_do_rs"

if [[ -x "$SIM_BIN" && -x "$EODO_BIN" ]]; then
    log "All binaries ready:"
    log "  $SIM_BIN"
    log "  $EODO_BIN"
    log "Environment ready. Try:"
    log "  $PY_BIN -c 'from thermalbits import ThermalBits; tb = ThermalBits(\"test_files/half_adder.v\"); print(tb.file_name, tb.pi, tb.po)'"
else
    err "Build finished but one of the binaries is missing"
    exit 1
fi
