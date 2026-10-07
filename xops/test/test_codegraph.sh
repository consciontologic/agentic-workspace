#!/usr/bin/env bash
# xops/test/test_codegraph.sh — tests for `make codeg`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$REPO_ROOT/xops/lib/log.sh"

PASS=0; FAIL=0

ok_if() {
  local desc="$1" cond="$2"
  if [[ "$cond" == "true" ]]; then
    log_ok "  PASS: $desc"
    (( PASS++ )) || true
  else
    log_err "  FAIL: $desc"
    (( FAIL++ )) || true
  fi
}

test_codeg_uses_available_runner() {
  local bin_dir log_file; bin_dir="$(mktemp -d)"; log_file="$bin_dir/invocation"
  cat > "$bin_dir/codegraph" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" > "${CODEGRAPH_TEST_LOG:?}"
exit 0
EOF
  chmod +x "$bin_dir/codegraph"

  local output="" got=0
  output="$(PATH="$bin_dir:$PATH" CODEGRAPH_TEST_LOG="$log_file" make --no-print-directory codeg 2>&1)" || got=$?

  ok_if "make codeg exits 0 with codegraph runner (got $got)" "$([[ $got -eq 0 ]] && echo true || echo false)"
  ok_if "make codeg logs success" "$([[ "$output" == *"index updated successfully"* ]] && echo true || echo false)"
  ok_if "make codeg logs index lifecycle" "$([[ "$output" == *"init local index"* || "$output" == *"sync local index"* ]] && echo true || echo false)"
  ok_if "make codeg initializes the repository" "$([[ "$(<"$log_file")" == "init ." ]] && echo true || echo false)"

  rm -rf "$bin_dir"
}

test_codeg_warns_without_runner() {
  local bin_dir python_path output="" got=0
  bin_dir="$(mktemp -d)"; python_path="$(command -v python3)"
  output="$(PATH="$bin_dir" "$python_path" "$REPO_ROOT/xops/makefile/codegraph_ops.py" update 2>&1)" || got=$?

  ok_if "codegraph warns when no runner is available" "$([[ $got -eq 1 && "$output" == *"neither codegraph nor npx is available"* ]] && echo true || echo false)"
  rm -rf "$bin_dir"
}

test_codeg_reports_runner_error() {
  local bin_dir python_path output="" got=0
  bin_dir="$(mktemp -d)"; python_path="$(command -v python3)"
  printf '#!/bin/bash\nexit 7\n' > "$bin_dir/codegraph"
  chmod +x "$bin_dir/codegraph"
  output="$(PATH="$bin_dir" "$python_path" "$REPO_ROOT/xops/makefile/codegraph_ops.py" update 2>&1)" || got=$?

  ok_if "codegraph reports runner errors" "$([[ $got -eq 7 && "$output" == *"failed (exit code 7)"* ]] && echo true || echo false)"
  rm -rf "$bin_dir"
}

test_codeg_uses_available_runner
test_codeg_warns_without_runner
test_codeg_reports_runner_error

printf '\n'
log_step "codegraph: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
