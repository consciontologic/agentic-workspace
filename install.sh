#!/usr/bin/env bash
# install.sh — one-liner installer for agentic-workspace
#
# Usage (curl):
#   curl -fsSL https://raw.githubusercontent.com/metaphy6/agentic-workspace/main/install.sh \
#     | bash -s -- --target my-repo
#
# Usage (local clone):
#   ./install.sh --target /path/to/your-project [scaffold options]
#
# Options (all forwarded to scaffold.sh):
#   --target PATH         Required. Directory to scaffold into.
#   --dry-run             Preview only; change nothing.
#   --force               Overwrite existing files.
#   --preset NAME         minimal | full  (default: full)
#   --agents LIST         Comma-separated: copilot,claude,codex,local (default: all)
#   --lang LANG           Add language preset: python | node | go | rust
#   --no-mcp              Skip MCP config files.
#   --no-vscode           Skip .vscode/ folder.
#   --no-skills           Skip .agents/skills/ tree.
#   -h | --help           This message.
#
# Environment variables:
#   AVB_REPO    Override clone URL (default: https://github.com/metaphy6/agentic-workspace.git)
#   AVB_BRANCH  Override branch     (default: main)
#   AVB_CACHE   Override local clone cache dir (default: ~/.cache/agentic-workspace)

set -euo pipefail

# ── config ───────────────────────────────────────────────────────────────
AVB_REPO="${AVB_REPO:-https://github.com/metaphy6/agentic-workspace.git}"
AVB_BRANCH="${AVB_BRANCH:-main}"
AVB_CACHE="${AVB_CACHE:-$HOME/.cache/agentic-workspace}"

# ── inline logging (mirrors xops/lib/log.sh — no source available yet) ──
if [[ -t 2 && -z "${NO_COLOR:-}" ]]; then
  _CR=$'\033[0m' _BOLD=$'\033[1m' _DIM=$'\033[2m'
  _RED=$'\033[31m' _GREEN=$'\033[32m' _YELLOW=$'\033[33m'
  _BLUE=$'\033[34m' _CYAN=$'\033[36m'
else
  _CR="" _BOLD="" _DIM="" _RED="" _GREEN="" _YELLOW="" _BLUE="" _CYAN=""
fi
log_step() { printf "${_CYAN}▶️ ${_CR} ${_BOLD}%s${_CR}\n" "$*" >&2; }
log_info()  { printf "${_BLUE}ℹ️ ${_CR} %s\n"                "$*" >&2; }
log_ok()    { printf "${_GREEN}✅${_CR} %s\n"                 "$*" >&2; }
log_warn()  { printf "${_YELLOW}⚠️ ${_CR} %s\n"              "$*" >&2; }
die()       { printf "${_RED}❌ %s${_CR}\n"                   "$*" >&2; exit "${2:-1}"; }

# ── help ─────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

# ── check deps ───────────────────────────────────────────────────────────
command -v git  >/dev/null 2>&1 || die "git is required"
command -v bash >/dev/null 2>&1 || die "bash is required"

# ── ensure framework source is available ─────────────────────────────────
SCAFFOLD=""

# If we're running from inside an already-cloned copy (local use):
if [[ -n "${BASH_SOURCE[0]:-}" && -f "$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/xops/init/scaffold.sh" ]]; then
  SCAFFOLD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/xops/init/scaffold.sh"
  log_info "Using local framework copy: $(dirname "$SCAFFOLD")"
else
  # Running via pipe (curl | bash) — need to clone/update the cache.
  log_step "Fetching agentic-workspace from $AVB_REPO@$AVB_BRANCH"
  if [[ -d "$AVB_CACHE/.git" ]]; then
    log_info "Updating cached clone at $AVB_CACHE"
    git -C "$AVB_CACHE" fetch --quiet origin "$AVB_BRANCH" 2>/dev/null \
      || log_warn "fetch failed — using cached version"
    git -C "$AVB_CACHE" reset --quiet --hard "origin/$AVB_BRANCH" 2>/dev/null || true
  else
    mkdir -p "$(dirname "$AVB_CACHE")"
    git clone --quiet --depth=1 --branch "$AVB_BRANCH" "$AVB_REPO" "$AVB_CACHE" \
      || die "Failed to clone $AVB_REPO. Check network access and the repo URL."
  fi
  SCAFFOLD="$AVB_CACHE/xops/init/scaffold.sh"
fi

[[ -f "$SCAFFOLD" ]] || die "scaffold.sh not found at $SCAFFOLD"
chmod +x "$SCAFFOLD"

log_ok "Framework source ready: $(dirname "$(dirname "$SCAFFOLD")")"

# ── delegate to scaffold.sh ───────────────────────────────────────────────
log_step "Running scaffold.sh $*"
"$SCAFFOLD" "$@"
