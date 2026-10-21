#!/usr/bin/env bash
# xops/test/test_ci.sh
# Runs the standalone ci/ pipeline-generator suite (python unittest) under the shared runner.

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

test_ci_unittest_suite_passes() {
  local rc=0 out
  out="$(cd "$REPO_ROOT" && python3 -m unittest discover -s ci/tests -p 'test_*.py' 2>&1)" || rc=$?
  ok_if "ci/tests unittest suite exits 0" "$([[ $rc -eq 0 ]] && echo true || echo false)"
  [[ $rc -eq 0 ]] || printf '%s\n' "$out" | tail -40 >&2
}

test_ci_is_not_wired_into_installers() {
  local hits
  hits="$(grep -lE '(^|[^a-z])ci/(apply|templates)' "$REPO_ROOT/install.sh" "$REPO_ROOT/xops/init/scaffold.sh" "$REPO_ROOT/xops/init/scaffold_codex.py" 2>/dev/null || true)"
  ok_if "install.sh/scaffold do not reference ci/" "$([[ -z "$hits" ]] && echo true || echo false)"
}

test_ci_unittest_suite_passes
test_ci_is_not_wired_into_installers

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL" >&2
[[ $FAIL -eq 0 ]]
