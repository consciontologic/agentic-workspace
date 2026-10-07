#!/usr/bin/env bash
# xops/test/test_scaffold_dryrun.sh
# Tests for xops/init/scaffold.sh --dry-run behavior.
#
# Verifies that --dry-run creates NO files in the target directory,
# still produces meaningful output, and exits 0.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCAFFOLD="$REPO_ROOT/xops/init/scaffold.sh"
source "$REPO_ROOT/xops/lib/log.sh"

PASS=0; FAIL=0

# ── helpers ───────────────────────────────────────────────────────────────
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

# ── test: --dry-run creates no files ──────────────────────────────────────
test_dryrun_no_files_created() {
  local target; target="$(mktemp -d)"

  bash "$SCAFFOLD" --target "$target" --dry-run >/dev/null 2>&1

  local count; count="$(find "$target" -mindepth 1 | wc -l)"
  ok_if "--dry-run creates 0 files in target (got $count)" "$([[ $count -eq 0 ]] && echo true || echo false)"

  rm -rf "$target"
}

# ── test: --dry-run exits 0 ───────────────────────────────────────────────
test_dryrun_exits_zero() {
  local target; target="$(mktemp -d)"
  local got=0

  bash "$SCAFFOLD" --target "$target" --dry-run >/dev/null 2>&1 || got=$?
  ok_if "--dry-run exits 0 (got $got)" "$([[ $got -eq 0 ]] && echo true || echo false)"

  rm -rf "$target"
}

# ── test: real run creates AGENTS.md in target ────────────────────────────
test_real_run_creates_agents_md() {
  local target; target="$(mktemp -d)"
  local got=0

  bash "$SCAFFOLD" --target "$target" >/dev/null 2>&1 || got=$?

  ok_if "real run exits 0 (got $got)" "$([[ $got -eq 0 ]] && echo true || echo false)"
  ok_if "real run creates AGENTS.md" "$([[ -f "$target/AGENTS.md" ]] && echo true || echo false)"

  rm -rf "$target"
}

# ── test: real run creates blank tracking.csv (header only) ───────────────
test_real_run_blank_tracking_csv() {
  local target; target="$(mktemp -d)"

  bash "$SCAFFOLD" --target "$target" >/dev/null 2>&1

  local lines=""
  if [[ -f "$target/docs/tracking/tracking.csv" ]]; then
    lines="$(wc -l < "$target/docs/tracking/tracking.csv")"
  fi
  ok_if "docs/tracking/tracking.csv exists after real run" "$([[ -f "$target/docs/tracking/tracking.csv" ]] && echo true || echo false)"
  ok_if "docs/tracking/tracking.csv is header-only (1 line, got $lines)" "$([[ "$lines" -eq 1 ]] && echo true || echo false)"

  rm -rf "$target"
}

# ── test: excluded vendor files are never scaffolded ─────────────────────
test_real_run_excludes_unmanaged_vendor_files() {
  local target; target="$(mktemp -d)"

  bash "$SCAFFOLD" --target "$target" >/dev/null 2>&1

  local rel
  for rel in \
    ".codex-plugin" \
    ".cursor" \
    ".opencode" \
    ".claude-plugin" \
    "gemini-extension.json" \
    "GEMINI.md"; do
    ok_if "real run never creates $rel" "$([[ ! -e "$target/$rel" ]] && echo true || echo false)"
  done

  for rel in \
    ".codex-plugin" \
    ".cursor" \
    ".opencode" \
    ".claude-plugin" \
    "gemini-extension.json" \
    "GEMINI.md"; do
    ok_if "source repo has no $rel" "$([[ ! -e "$REPO_ROOT/$rel" ]] && echo true || echo false)"
  done

  rm -rf "$target"
}

# ── test: --force re-creates files ────────────────────────────────────────
test_force_flag_overwrites() {
  local target; target="$(mktemp -d)"

  # First run
  bash "$SCAFFOLD" --target "$target" >/dev/null 2>&1
  # Mutate a file
  printf 'MODIFIED\n' > "$target/AGENTS.md"
  # Second run without --force should keep modification
  bash "$SCAFFOLD" --target "$target" >/dev/null 2>&1
  local kept; kept="$(head -1 "$target/AGENTS.md")"
  ok_if "without --force, existing file is kept" "$([[ "$kept" == "MODIFIED" ]] && echo true || echo false)"

  # Third run with --force should overwrite
  bash "$SCAFFOLD" --target "$target" --force >/dev/null 2>&1
  local forced; forced="$(head -1 "$target/AGENTS.md")"
  ok_if "--force overwrites existing file" "$([[ "$forced" != "MODIFIED" ]] && echo true || echo false)"

  rm -rf "$target"
}

# ── test: --no-skills skips .agents/ ──────────────────────────────────────
test_no_skills_flag() {
  local target; target="$(mktemp -d)"

  bash "$SCAFFOLD" --target "$target" --no-skills >/dev/null 2>&1

  ok_if "--no-skills: no skill SKILL.md files created" "$(
    count="$(find "$target/.agents/skills" -name 'SKILL.md' 2>/dev/null | wc -l)"
    [[ "$count" -eq 0 ]] && echo true || echo false
  )"

  rm -rf "$target"
}

# ── run all tests ──────────────────────────────────────────────────────────
test_dryrun_no_files_created
test_dryrun_exits_zero
test_real_run_creates_agents_md
test_real_run_blank_tracking_csv
test_real_run_excludes_unmanaged_vendor_files
test_force_flag_overwrites
test_no_skills_flag

printf '\n'
log_step "scaffold_dryrun: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
