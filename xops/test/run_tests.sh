#!/usr/bin/env bash
# xops/test/run_tests.sh — run every test_*.sh in this directory and report.
#
# Usage:
#   bash xops/test/run_tests.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib/log.sh
source "$REPO_ROOT/xops/lib/log.sh"

# ── discover test files ──────────────────────────────────────────────────
mapfile -t TEST_FILES < <(find "$SCRIPT_DIR" -maxdepth 1 -name 'test_*.sh' | sort)

if [[ ${#TEST_FILES[@]} -eq 0 ]]; then
  log_warn "No test_*.sh files found in $SCRIPT_DIR"
  exit 0
fi

# ── run each test file, collect results ──────────────────────────────────
PASS=0
FAIL=0
ERRORS=()

for test_file in "${TEST_FILES[@]}"; do
  name="$(basename "$test_file")"
  log_step "$name"
  if bash "$test_file"; then
    log_ok "  PASS: $name"
    (( PASS++ )) || true
  else
    log_err "  FAIL: $name"
    (( FAIL++ )) || true
    ERRORS+=("$name")
  fi
done

# ── summary ──────────────────────────────────────────────────────────────
printf '\n'
log_step "Results: $PASS passed, $FAIL failed"
if [[ ${#ERRORS[@]} -gt 0 ]]; then
  for e in "${ERRORS[@]}"; do
    log_err "  failed: $e"
  done
  exit 1
fi
log_ok "All tests passed."
