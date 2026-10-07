#!/usr/bin/env bash
# xops/test/test_log.sh
# Tests for xops/lib/log.sh — verify every exported function works
# and that NO_COLOR suppresses ANSI codes, and AVB_LOG_QUIET suppresses output.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PASS=0; FAIL=0

ok_if() {
  local desc="$1" cond="$2"
  if [[ "$cond" == "true" ]]; then
    printf '  ✅ PASS: %s\n' "$desc" >&2
    (( PASS++ )) || true
  else
    printf '  ❌ FAIL: %s\n' "$desc" >&2
    (( FAIL++ )) || true
  fi
}

# ── helper: run log function and capture stderr ────────────────────────────
capture_log() {
  # Runs a subshell that sources log.sh and calls $1 with args $2…
  local fn="$1"; shift
  NO_COLOR=1 bash -c "
    source '$REPO_ROOT/xops/lib/log.sh'
    $fn \"\$@\" 2>&1
  " -- "$@"
}

# ── test: log_ok produces output ──────────────────────────────────────────
test_log_ok_produces_output() {
  local out; out="$(capture_log log_ok "hello world")"
  ok_if "log_ok produces output" "$([[ -n "$out" ]] && echo true || echo false)"
  ok_if "log_ok contains message text" "$([[ "$out" == *"hello world"* ]] && echo true || echo false)"
}

test_log_err_produces_output() {
  local out; out="$(capture_log log_err "something broke")"
  ok_if "log_err produces output" "$([[ -n "$out" ]] && echo true || echo false)"
  ok_if "log_err contains message text" "$([[ "$out" == *"something broke"* ]] && echo true || echo false)"
}

test_log_warn_produces_output() {
  local out; out="$(capture_log log_warn "be careful")"
  ok_if "log_warn produces output" "$([[ -n "$out" ]] && echo true || echo false)"
}

test_log_step_produces_output() {
  local out; out="$(capture_log log_step "step heading")"
  ok_if "log_step produces output" "$([[ -n "$out" ]] && echo true || echo false)"
  ok_if "log_step contains heading text" "$([[ "$out" == *"step heading"* ]] && echo true || echo false)"
}

test_log_info_produces_output() {
  local out; out="$(capture_log log_info "info msg")"
  ok_if "log_info produces output" "$([[ -n "$out" ]] && echo true || echo false)"
}

test_log_dim_produces_output() {
  local out; out="$(capture_log log_dim "dim text")"
  ok_if "log_dim produces output" "$([[ -n "$out" ]] && echo true || echo false)"
}

# ── test: AVB_LOG_QUIET suppresses output ─────────────────────────────────
test_quiet_mode_suppresses_output() {
  local out
  out="$(NO_COLOR=1 AVB_LOG_QUIET=1 bash -c "
    source '$REPO_ROOT/xops/lib/log.sh'
    log_ok 'should be silent' 2>&1
  ")"
  ok_if "AVB_LOG_QUIET=1 suppresses log_ok" "$([[ -z "$out" ]] && echo true || echo false)"
}

# ── test: NO_COLOR removes ANSI escape codes ──────────────────────────────
test_no_color_removes_ansi() {
  local out
  out="$(NO_COLOR=1 bash -c "
    source '$REPO_ROOT/xops/lib/log.sh'
    log_ok 'colored msg' 2>&1
  ")"
  # ANSI codes contain ESC (\033) — should be absent when NO_COLOR=1
  if printf '%s' "$out" | grep -qP '\x1b'; then
    ok_if "NO_COLOR=1 removes ANSI codes" "false"
  else
    ok_if "NO_COLOR=1 removes ANSI codes" "true"
  fi
}

# ── test: die exits non-zero ──────────────────────────────────────────────
test_die_exits_nonzero() {
  local got=0
  NO_COLOR=1 bash -c "
    source '$REPO_ROOT/xops/lib/log.sh'
    die 'fatal error' 42
  " >/dev/null 2>&1 || got=$?
  ok_if "die exits with provided code (got $got)" "$([[ "$got" -eq 42 ]] && echo true || echo false)"
}

# ── test: die defaults to exit 1 ─────────────────────────────────────────
test_die_defaults_exit_1() {
  local got=0
  NO_COLOR=1 bash -c "
    source '$REPO_ROOT/xops/lib/log.sh'
    die 'fatal'
  " >/dev/null 2>&1 || got=$?
  ok_if "die defaults to exit 1 (got $got)" "$([[ "$got" -eq 1 ]] && echo true || echo false)"
}

# ── test: double-source is safe (guard works) ─────────────────────────────
test_double_source_is_safe() {
  local got=0
  NO_COLOR=1 bash -c "
    source '$REPO_ROOT/xops/lib/log.sh'
    source '$REPO_ROOT/xops/lib/log.sh'
    log_ok 'still works'
  " >/dev/null 2>&1 || got=$?
  ok_if "double-source is safe (exit $got)" "$([[ "$got" -eq 0 ]] && echo true || echo false)"
}

# ── test: no caller treats log_* as a printf format string ────────────────
# _emit prints with `printf '%s\n' "$*"`, so format specifiers are never
# interpreted and trailing args are appended verbatim. Callers must interpolate.
test_no_caller_passes_printf_format_args() {
  local offenders=""
  offenders="$(grep -rnE '\blog_(info|ok|warn|err|step|dim) +"[^"]*%[a-z][^"]*" +"' \
    --include='*.sh' "$REPO_ROOT/xops" 2>/dev/null || true)"
  ok_if "no log_* caller passes printf-style format args" \
    "$([[ -z "$offenders" ]] && echo true || echo false)"
  [[ -z "$offenders" ]] || printf '     offenders:\n%s\n' "$offenders" >&2
}

# ── run all ───────────────────────────────────────────────────────────────
test_log_ok_produces_output
test_log_err_produces_output
test_log_warn_produces_output
test_log_step_produces_output
test_log_info_produces_output
test_log_dim_produces_output
test_quiet_mode_suppresses_output
test_no_color_removes_ansi
test_die_exits_nonzero
test_die_defaults_exit_1
test_double_source_is_safe
test_no_caller_passes_printf_format_args

printf '\n'
printf '▶️  log: %d passed, %d failed\n' "$PASS" "$FAIL" >&2
[[ "$FAIL" -eq 0 ]]
