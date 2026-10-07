#!/usr/bin/env bash
# xops/init/scaffold.sh
#
# The bootstrapper. Drops the agentic-workspace framework into a target
# repo. Idempotent: safe to re-run after upstream changes.
#
# Usage:
#   xops/init/scaffold.sh --target /path/to/repo [options]
#   xops/init/scaffold.sh              # interactive TUI (no args)
#
# Options:
#   --target PATH         Required (or set interactively). Directory to install into.
#   --dry-run             Show what would happen, change nothing.
#   --force               Overwrite files that already exist at the target.
#   --preset NAME         minimal | full   (default: full)
#   --agents LIST         Comma-separated list of agents to wire (default: all).
#                         Choices: copilot,claude,codex,local
#   --lang LANG           Language preset: python | node | go | rust
#                         Adds .gitignore lines, Makefile.lang.mk, and starter test command.
#   --no-mcp              Skip MCP config files.
#   --no-vscode           Skip .vscode/ folder.
#   --no-skills           Skip .agents/skills/ (just leave a README).
#   -h | --help           This message.
#
# What gets installed (full preset):
#   - Root: LICENSE, AGENTS.md, CLAUDE.md, CONVENTIONS.md,
#           Makefile, .gitignore, .gitattributes
#           (README.md is NOT copied — a project-template README is written instead)
#   - .github/        copilot-instructions.md + agents/ + prompts/
#   - .vscode/        settings, tasks, mcp
#   - Vendor configs  matching --agents
#   - docs/tracking/  tracking.csv + schema + context + state/
#   - xops/           bash + python ops tree (this script itself + siblings)
#   - docs/           code/ project/ design/ planning/ROADMAP.md tracking/ guides/
#   - .agents/skills/ skill library (one SKILL.md per subfolder)
#
# After install, in the target repo:
#   make help          # see available targets
#   xops/agent/session-bootstrap.sh   # first context-load

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_ROOT="$(cd "$HERE/../.." && pwd)"
# shellcheck source=../lib/log.sh
source "$SRC_ROOT/xops/lib/log.sh"

# ── defaults ────────────────────────────────────────────────────────────
TARGET=""
DRY_RUN=0
FORCE=0
PRESET="full"
AGENTS="copilot,claude,codex,local"
WITH_MCP=1
WITH_VSCODE=1
WITH_SKILLS=1
LANG=""

# ── arg parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)     TARGET="$2"; shift 2 ;;
    --target=*)   TARGET="${1#*=}"; shift ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --force)      FORCE=1; shift ;;
    --preset)     PRESET="$2"; shift 2 ;;
    --preset=*)   PRESET="${1#*=}"; shift ;;
    --agents)     AGENTS="$2"; shift 2 ;;
    --agents=*)   AGENTS="${1#*=}"; shift ;;
    --lang)       LANG="$2"; shift 2 ;;
    --lang=*)     LANG="${1#*=}"; shift ;;
    --no-mcp)     WITH_MCP=0; shift ;;
    --no-vscode)  WITH_VSCODE=0; shift ;;
    --no-skills)  WITH_SKILLS=0; shift ;;
    -h|--help)    sed -n '2,45p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)            die "unknown arg: $1 (try --help)" 64 ;;
  esac
done

# ── interactive TUI when no --target given ───────────────────────────────
_ask() {
  # _ask PROMPT DEFAULT
  local prompt="$1" default="${2:-}"
  local answer
  if [[ -n "$default" ]]; then
    printf "%s [%s]: " "$prompt" "$default" >&2
  else
    printf "%s: " "$prompt" >&2
  fi
  read -r answer </dev/tty
  echo "${answer:-$default}"
}

_ask_yn() {
  local prompt="$1" default="${2:-y}"
  local answer
  printf "%s [%s]: " "$prompt" "$default" >&2
  read -r answer </dev/tty
  answer="${answer:-$default}"
  [[ "$answer" =~ ^[Yy] ]] && echo "1" || echo "0"
}

_tui_select() {
  # _tui_select PROMPT item1 item2 ...  → prints chosen item
  local prompt="$1"; shift
  local items=("$@")
  local i choice
  printf "\n%s\n" "$prompt" >&2
  for i in "${!items[@]}"; do
    printf "  %d) %s\n" "$((i+1))" "${items[$i]}" >&2
  done
  printf "choice [1]: " >&2
  read -r choice </dev/tty
  choice="${choice:-1}"
  echo "${items[$((choice-1))]}"
}

if [[ -z "$TARGET" ]]; then
  # Try dialog/whiptail first for a nicer experience.
  if command -v whiptail >/dev/null 2>&1 || command -v dialog >/dev/null 2>&1; then
    _TOOL="whiptail"; command -v whiptail >/dev/null 2>&1 || _TOOL="dialog"
    TARGET=$($_TOOL --inputbox "Target directory (will be created if missing):" 8 60 "./my-project" 3>&1 1>&2 2>&3) || TARGET=""
    PRESET=$($_TOOL --menu "Preset:" 12 50 2 \
      "full"    "All framework files (default)" \
      "minimal" "Rulebooks + tracking only" 3>&1 1>&2 2>&3) || PRESET="full"
    LANG=$($_TOOL --menu "Language preset:" 14 50 5 \
      ""       "(none)" \
      "python" "Python"  \
      "node"   "Node.js" \
      "go"     "Go"      \
      "rust"   "Rust"    3>&1 1>&2 2>&3) || LANG=""
    [[ "$LANG" == "(none)" ]] && LANG=""
    WITH_MCP=$($_TOOL --yesno "Include MCP config files?" 7 40 3>&1 1>&2 2>&3 && echo 1 || echo 0)
  else
    # Plain read -p fallback.
    printf "\n${BOLD}🏗  agentic-workspace interactive setup${RESET}\n\n" >&2
    TARGET=$(_ask "Target directory" "./my-project")
    PRESET=$(_tui_select "Choose preset:" "full" "minimal")
    LANG=$(_tui_select "Language preset (choose 1 for none):" "(none)" "python" "node" "go" "rust")
    [[ "$LANG" == "(none)" ]] && LANG=""
    WITH_MCP=$(_ask_yn "Include MCP config?" "y")
    WITH_VSCODE=$(_ask_yn "Include .vscode/ folder?" "y")
    WITH_SKILLS=$(_ask_yn "Include .agents/skills/ library?" "y")
  fi
fi

[[ -n "$TARGET" ]] || die "--target is required (or run interactively)" 64
case "$PRESET" in minimal|full) ;; *) die "--preset must be minimal|full" 64 ;; esac
IFS=',' read -r -a _selected_agents <<< "$AGENTS"
for _agent in "${_selected_agents[@]}"; do
  case "$_agent" in copilot|claude|codex|local) ;; *) die "unknown agent: $_agent" 64 ;; esac
done
command -v python3 >/dev/null 2>&1 || die "python3 is required for scaffold configuration" 69
if [[ -n "$LANG" ]]; then
  case "$LANG" in python|node|go|rust) ;; *) die "--lang must be python|node|go|rust" 64 ;; esac
fi

# Convert relative target to absolute.
TARGET="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$TARGET")"
if [[ $DRY_RUN -eq 0 ]]; then
  mkdir -p "$TARGET"
fi

if [[ "$SRC_ROOT" == "$TARGET" ]]; then
  warn "source == target — this is a re-scaffold of the framework repo itself"
fi

log_step "🏗  agentic-workspace scaffolder"
log_info "  source : $SRC_ROOT"
log_info "  target : $TARGET"
log_info "  preset : $PRESET"
log_info "  agents : $AGENTS"
log_info "  lang   : ${LANG:-(none)}"
log_info "  options: mcp=$WITH_MCP vscode=$WITH_VSCODE skills=$WITH_SKILLS"
log_info "  mode   : $( ((DRY_RUN)) && echo DRY-RUN || echo LIVE )$( ((FORCE)) && echo " +force" )"
echo >&2

# ── copy helpers ────────────────────────────────────────────────────────
copy_file() {
  local rel="$1"
  local src="$SRC_ROOT/$rel"
  local dst="$TARGET/$rel"

  if [[ ! -e "$src" ]]; then
    log_warn "  ⚠️  source missing: $rel (skipping)"
    return 0
  fi

  if [[ -e "$dst" && $FORCE -eq 0 ]]; then
    if cmp -s "$src" "$dst"; then
      log_dim "  ✓ identical: $rel"
    else
      log_dim "  ↩ kept user version: $rel (use --force to overwrite)"
    fi
    return 0
  fi

  if [[ $DRY_RUN -eq 1 ]]; then
    log_info "  + would copy: $rel"
    return 0
  fi

  mkdir -p "$(dirname "$dst")"
  cp -a "$src" "$dst"
  log_ok "  + copied: $rel"
}

copy_glob() {
  local pattern="$1"
  shopt -s globstar nullglob
  local f
  for f in $SRC_ROOT/$pattern; do
    [[ -f "$f" ]] || continue
    copy_file "${f#$SRC_ROOT/}"
  done
  shopt -u globstar nullglob
}

want_agent() {
  case ",$AGENTS," in *",$1,"*) return 0 ;; esac
  return 1
}

# ── 1. root files ───────────────────────────────────────────────────────
log_step "📦 root files"
# Intentionally NOT copied: README.md (a project template is written below),
# install.sh, .agentic-workspace-version (framework-only artefacts).
ROOT_FILES=(
  "LICENSE" "AGENTS.md" "Makefile"
  ".gitignore" ".gitattributes"
)
for f in "${ROOT_FILES[@]}"; do copy_file "$f"; done

# Write a project-template README.md (only if target has none, unless --force).
_dst_readme="$TARGET/README.md"
_target_name="$(basename "$TARGET")"
if [[ -e "$_dst_readme" && $FORCE -eq 0 ]]; then
  log_dim "  ↩ kept user version: README.md"
elif [[ $DRY_RUN -eq 1 ]]; then
  log_info "  + would write: README.md (project template)"
else
  cat > "$_dst_readme" <<README_EOF
# $_target_name

> _Describe what this project does in one sentence._

## Quickstart

\`\`\`bash
# install dependencies (edit for your stack)
\`\`\`

## Documentation

- [\`AGENTS.md\`](AGENTS.md) — rules every AI coding assistant follows in this repo.
- [\`docs/planning/ROADMAP.md\`](docs/planning/ROADMAP.md) — the plan.
- [\`docs/tracking/README.md\`](docs/tracking/README.md) — how the tracking log works.
- [\`docs/tracking/context.md\`](docs/tracking/context.md) — project context pack.
- [\`.agents/skills/README.md\`](.agents/skills/README.md) — curated skill library.

## Common commands

\`\`\`bash
make help            # list available targets
make git.dry         # preview pending commits (read-only)
make git             # commit pending tracking rows + push
make track.add ACTION=note SUMMARY="..."
\`\`\`

## License

See [\`LICENSE\`](LICENSE).
README_EOF
  log_ok "  + wrote: README.md (project template for '$_target_name')"
fi

# Vendor entrypoint files — only for selected agents.
want_agent claude  && copy_file "CLAUDE.md"
# CONVENTIONS.md is a generic vendor entry point, not tied to a specific agent.
copy_file "CONVENTIONS.md"

# ── 2. .github/ ─────────────────────────────────────────────────────────
if want_agent copilot || want_agent codex; then
  log_step "🐙 .github/ (shared workflow sources)"
  copy_file ".github/copilot-instructions.md"
  copy_glob ".github/agents/*.agent.md"
  copy_glob ".github/prompts/*.prompt.md"
  copy_glob ".github/instructions/*.instructions.md"
fi
copy_glob ".agents/instructions/*.md"

# ── 3. .vscode/ ─────────────────────────────────────────────────────────
if [[ $WITH_VSCODE -eq 1 ]]; then
  log_step "🖥  .vscode/"
  copy_file ".vscode/settings.json"
  copy_file ".vscode/tasks.json"
  if [[ $WITH_MCP -eq 1 ]]; then
    # Write a .vscode/mcp.json WITHOUT the codegraph server.
    # VS Code reads BOTH .vscode/mcp.json AND .mcp.json — if codegraph appears
    # in both, VS Code creates two competing "codegraph" MCP servers.  The one
    # from .mcp.json (workspace-dot-mcp) shows a Trust prompt; if it starts
    # inactive (wrong path / stale cache) Copilot shows no tools and the server
    # disappears from the panel.  Keeping codegraph only in .mcp.json (with the
    # absolute path baked in below) eliminates the conflict.
    _dst_vscode_mcp="$TARGET/.vscode/mcp.json"
    if [[ -e "$_dst_vscode_mcp" && $FORCE -eq 0 ]]; then
      log_dim "  ↩ kept user version: .vscode/mcp.json"
    elif [[ $DRY_RUN -eq 1 ]]; then
      log_info "  + would write: .vscode/mcp.json (no codegraph — already in .mcp.json)"
    else
      mkdir -p "$TARGET/.vscode"
      cat > "$_dst_vscode_mcp" <<'VSCODE_MCP_EOF'
{
  "$schema": "https://modelcontextprotocol.io/schema/mcp.json",
  "$comment": "VS Code Copilot MCP config. VS Code reads both this file and .mcp.json — codegraph is defined only in .mcp.json (with the project's absolute path baked in by scaffold.sh) to avoid duplicate servers. Add other project-specific MCP servers here.",
  "servers": {},
  "inputs": []
}
VSCODE_MCP_EOF
      log_ok "  + wrote: .vscode/mcp.json (codegraph in .mcp.json only)"
    fi
  fi
fi

# ── 4. vendor MCP + plugin configs ──────────────────────────────────────
if [[ $WITH_MCP -eq 1 ]]; then
  log_step "🔌 MCP"
  # Write a project-specific .mcp.json with the absolute target path baked in.
  # VS Code reads this file directly (workspace-dot-mcp servers) in addition to
  # .vscode/mcp.json — so this is the single source of truth for codegraph across
  # ALL clients (Claude Code, Cursor, VS Code Copilot).  The absolute path is
  # required because non-VS Code clients don't expand ${workspaceFolder} and
  # launch the MCP server with an unpredictable CWD.
fi

_config_args=(--source "$SRC_ROOT" --target "$TARGET")
want_agent codex && _config_args+=(--codex)
[[ $WITH_MCP -eq 1 ]] && _config_args+=(--mcp)
[[ $WITH_SKILLS -eq 1 ]] && _config_args+=(--skills)
[[ $DRY_RUN -eq 1 ]] && _config_args+=(--dry-run)
[[ $FORCE -eq 1 ]] && _config_args+=(--force)
python3 "$SRC_ROOT/xops/init/scaffold_codex.py" "${_config_args[@]}"

# ── 5. docs/tracking/ ─────────────────────────────────────────────────────────────
log_step "📋 docs/tracking/"
# Always write a BLANK tracking.csv (just the header) — never copy the source
# repo's history into a freshly scaffolded project.
if [[ $DRY_RUN -eq 0 ]]; then
  mkdir -p "$TARGET/docs/tracking/state"
  BLANK_CSV="$TARGET/docs/tracking/tracking.csv"
  if [[ -e "$BLANK_CSV" && $FORCE -eq 0 ]]; then
    log_dim "  ↩ kept user version: docs/tracking/tracking.csv (use --force to reset)"
  else
    printf 'ts_utc,run_id,agent,scope,action,status,summary,refs,commit_sha\n' > "$BLANK_CSV"
    log_ok "  + created: docs/tracking/tracking.csv (blank)"
  fi
else
  log_info "  + would create: docs/tracking/tracking.csv (blank header only)"
fi
copy_file "docs/tracking/tracking.schema.md"
copy_file "docs/tracking/README.md"
copy_file "docs/tracking/state/.gitkeep"
copy_file "docs/tracking/context.md"

# ── 6. xops/ ────────────────────────────────────────────────────────────
log_step "🛠  xops/"
copy_file "xops/README.md"
copy_file "xops/lib/log.sh"
copy_glob "xops/agent/*.sh"
copy_glob "xops/makefile/*.py"

# Ensure executable bits stick after copy.
if [[ $DRY_RUN -eq 0 ]]; then
  chmod +x \
    "$TARGET/xops/agent/"*.sh 2>/dev/null || true
fi

# ── 7. docs/ ────────────────────────────────────────────────────────────
log_step "📚 docs/"
copy_file "docs/README.md"
copy_glob "docs/code/*.md"
copy_glob "docs/project/*.md"
copy_glob "docs/design/*.md"
copy_file "docs/planning/README.md"
copy_file "docs/planning/ROADMAP.md"
copy_file "docs/tracking/README.md"
copy_glob "docs/guides/*.md"
copy_file "docs/reports/README.md"

if [[ $WITH_SKILLS -eq 1 ]]; then
  log_step "🧠 .agents/skills/"
  copy_file ".agents/skills/README.md"
  # Each skill lives in its own subfolder as SKILL.md
  copy_glob ".agents/skills/**/*"
else
  copy_file ".agents/skills/README.md"
fi

# ── done ────────────────────────────────────────────────────────────────
# The .agentic-workspace-version stamp and install.sh are intentionally NOT
# copied into the target — those are framework-only artefacts. The target
# stands on its own once scaffolded.

# ── 8. language preset ───────────────────────────────────────────────────────────
if [[ -n "$LANG" ]]; then
  log_step "🗣  language preset: $LANG"
  _lang_mk="$TARGET/Makefile.lang.mk"
  _gitignore="$TARGET/.gitignore"

  if [[ $DRY_RUN -eq 0 ]]; then
    # .gitignore additions (appended only if not already present)
    _append_gitignore() {
      local line="$1"
      grep -qxF "$line" "$_gitignore" 2>/dev/null || echo "$line" >> "$_gitignore"
    }

    case "$LANG" in
      python)
        _append_gitignore "__pycache__/"
        _append_gitignore "*.py[cod]"
        _append_gitignore ".venv/"
        _append_gitignore "dist/"
        _append_gitignore "*.egg-info/"
        _append_gitignore ".pytest_cache/"
        _append_gitignore ".mypy_cache/"
        cat > "$_lang_mk" <<'EOF'
# Makefile.lang.mk — python preset (included by Makefile)
PYTHON ?= python3
VENV   ?= .venv

## test          Run the test suite
test:
	@$(PYTHON) -m pytest -q

## lint          Run ruff + mypy
lint:
	@$(PYTHON) -m ruff check .
	@$(PYTHON) -m mypy .

## venv          Create .venv and install deps
venv:
	@$(PYTHON) -m venv $(VENV)
	@$(VENV)/bin/pip install -q -e ".[dev]"
EOF
        ;;
      node)
        _append_gitignore "node_modules/"
        _append_gitignore "dist/"
        _append_gitignore ".next/"
        _append_gitignore "coverage/"
        cat > "$_lang_mk" <<'EOF'
# Makefile.lang.mk — node preset (included by Makefile)

## test          Run the test suite
test:
	@npm test

## lint          Run eslint
lint:
	@npm run lint

## build         Build the project
build:
	@npm run build
EOF
        ;;
      go)
        _append_gitignore "bin/"
        _append_gitignore "*.test"
        _append_gitignore "*.out"
        cat > "$_lang_mk" <<'EOF'
# Makefile.lang.mk — go preset (included by Makefile)

## test          Run go test ./...
test:
	@go test ./... -count=1

## lint          Run golangci-lint
lint:
	@golangci-lint run ./...

## build         Build the binary
build:
	@go build -o bin/$(notdir $(CURDIR)) ./...
EOF
        ;;
      rust)
        _append_gitignore "target/"
        _append_gitignore "Cargo.lock"
        cat > "$_lang_mk" <<'EOF'
# Makefile.lang.mk — rust preset (included by Makefile)

## test          Run cargo test
test:
	@cargo test

## lint          Run clippy
lint:
	@cargo clippy -- -D warnings

## build         Build in release mode
build:
	@cargo build --release
EOF
        ;;
    esac
    log_ok "  + Makefile.lang.mk ($LANG)"
    log_ok "  + .gitignore updated"
  else
    log_info "  + would write: Makefile.lang.mk ($LANG)"
    log_info "  + would update: .gitignore"
  fi
fi

echo >&2
log_ok "🎉 scaffold complete → $TARGET"
echo >&2
log_info "Next steps:"
log_dim  "  cd $TARGET"
log_dim  "  make help"
log_dim  "  xops/agent/session-bootstrap.sh"

# ── 9. CodeGraph index ──────────────────────────────────────────────────
# CodeGraph gives AI agents a pre-indexed code knowledge graph so they can
# answer "how does X work?" questions with ~58% fewer tool calls and ~16%
# lower token cost — 100% local, no API key needed.
# The MCP server config (--path ${workspaceFolder}) is already in place from
# step 4; this step builds the .codegraph/ index so the server can open it.
if [[ $WITH_MCP -eq 1 && $DRY_RUN -eq 0 ]]; then
  echo >&2
  log_step "🔍 CodeGraph index"

  # Resolve a codegraph runner: prefer a global install, fall back to npx.
  _CG_CMD=""
  if command -v codegraph >/dev/null 2>&1; then
    _CG_CMD="codegraph"
  elif command -v npx >/dev/null 2>&1; then
    _CG_CMD="npx -y @colbymchenry/codegraph"
  fi

  if [[ -n "$_CG_CMD" ]]; then
    if $_CG_CMD init "$TARGET" >/dev/null 2>&1; then
      log_ok "  Index built → $TARGET/.codegraph/"
    else
      log_warn "  codegraph init failed — run manually inside the project:"
      log_dim  "  npx @colbymchenry/codegraph init ."
    fi
  else
    log_warn "  Neither codegraph nor npx found — index not built."
    log_dim  "  Install Node.js, then: npx @colbymchenry/codegraph init ."
  fi
fi
