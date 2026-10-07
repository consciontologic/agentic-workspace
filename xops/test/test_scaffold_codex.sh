#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$REPO_ROOT/xops/lib/log.sh"
PASS=0; FAIL=0
mkdir -p /tmp/agent-runs
TEST_ROOT="$(mktemp -d /tmp/agent-runs/scaffold-codex.XXXXXX)"
trap 'rm -rf "$TEST_ROOT"' EXIT

run_install() {
  if bash "$REPO_ROOT/install.sh" "$@" > "$TEST_ROOT/install.log" 2>&1; then
    return 0
  else
    local status=$?
    cat "$TEST_ROOT/install.log"
    return "$status"
  fi
}

ok_if() {
  local desc="$1" cond="$2"
  if [[ "$cond" == "true" ]]; then
    log_ok "PASS: $desc"
    PASS=$((PASS + 1))
  else
    log_err "FAIL: $desc"
    FAIL=$((FAIL + 1))
  fi
}

test_codex_install() {
  local target="$TEST_ROOT/project"
  run_install --target "$target" --agents codex --no-vscode
  local rel
  for rel in AGENTS.md CONVENTIONS.md .codex/config.toml \
    .codex/agents/planner.toml .codex/agents/implementer.toml \
    .codex/agents/reviewer.toml .codex/agents/verifier.toml \
    .agents/skills/avb-plan/SKILL.md .agents/skills/avb-implement/SKILL.md \
    .agents/skills/test-driven-development/SKILL.md \
    .github/instructions/tests.instructions.md docs/guides/CODEX_SETUP.md; do
    ok_if "Codex installs $rel" "$([[ -f "$target/$rel" ]] && echo true || echo false)"
  done
  ok_if "installer removes framework machinery" "$([[ ! -e "$target/xops/init" && ! -e "$target/install.sh" ]] && echo true || echo false)"
}

test_native_formats() {
  local target="$TEST_ROOT/project"
  local got=0
  python3 - "$REPO_ROOT" "$target" <<'PY' || got=$?
import json
import sys
import tomllib
from pathlib import Path

source, target = map(Path, sys.argv[1:])
config = tomllib.loads((target / '.codex/config.toml').read_text())
assert config['approval_policy'] == 'on-request'
assert config['sandbox_mode'] == 'workspace-write'
server = config['mcp_servers']['codegraph']
assert server['args'][-2:] == ['--path', str(target)]
assert server['cwd'] == str(target)
generic = json.loads((target / '.mcp.json').read_text())
assert generic['mcpServers']['codegraph']['args'][-2:] == ['--path', str(target)]
assert server.get('env') == generic['mcpServers']['codegraph']['env'], 'Codex must preserve CodeGraph tool-selection environment'
for instruction in (source / '.github/instructions').glob('*.instructions.md'):
    relative = instruction.relative_to(source)
    assert str(relative) in config['developer_instructions']
    assert (target / relative).read_bytes() == instruction.read_bytes()
for agent in (source / '.github/agents').glob('*.agent.md'):
    name = agent.name.removesuffix('.agent.md')
    native = tomllib.loads((target / f'.codex/agents/{name}.toml').read_text())
    assert native['name'] == name
    assert native['description']
    assert str(agent.relative_to(source)) in native['developer_instructions']
    assert 'coordinating parent' in native['developer_instructions']
    if name == 'reviewer':
        assert native['sandbox_mode'] == 'read-only'
for prompt in (source / '.github/prompts').glob('*.prompt.md'):
    name = prompt.name.removesuffix('.prompt.md')
    folder = target / f'.agents/skills/avb-{name}'
    skill = (folder / 'SKILL.md').read_text()
    assert f'name: avb-{name}\n' in skill
    assert f'../../../{prompt.relative_to(source)}' in skill
    assert 'allow_implicit_invocation: false' in (folder / 'agents/openai.yaml').read_text()
    assert (target / prompt.relative_to(source)).read_bytes() == prompt.read_bytes()
for asset in (source / '.agents/skills').rglob('*'):
    if asset.is_file():
        assert (target / asset.relative_to(source)).read_bytes() == asset.read_bytes()
assert (target / '.agents/instructions/ROADMAP_DISCIPLINE.md').is_file()
assert not (target / '.vscode').exists()
PY
  ok_if "native TOML, every agent/prompt/instruction, and skill assets validate" "$([[ $got -eq 0 ]] && echo true || echo false)"
}

test_defaults_and_optouts() {
  local target="$TEST_ROOT/default"
  run_install --target "$target" --no-mcp --no-skills
  ok_if "default selection includes Codex" "$([[ -f "$target/.codex/config.toml" ]] && echo true || echo false)"
  ok_if "default retains Copilot and Claude" "$([[ -f "$target/.github/copilot-instructions.md" && -f "$target/CLAUDE.md" ]] && echo true || echo false)"
  ok_if "no-skills excludes native prompt adapters" "$([[ ! -e "$target/.agents/skills/avb-plan" && ! -e "$target/.agents/skills/test-driven-development" ]] && echo true || echo false)"
  ok_if "no-mcp excludes generic config and index" "$([[ ! -e "$target/.mcp.json" && ! -e "$target/.codegraph" ]] && echo true || echo false)"
  local got=0
  python3 - "$target/.codex/config.toml" <<'PY' || got=$?
import sys
import tomllib
from pathlib import Path
config = tomllib.loads(Path(sys.argv[1]).read_text())
assert 'mcp_servers' not in config
assert 'MCP was explicitly disabled' in config['developer_instructions']
assert 'Skills were explicitly disabled' in config['developer_instructions']
PY
  ok_if "Codex opt-outs parse and override tool requirements" "$([[ $got -eq 0 ]] && echo true || echo false)"
  run_install --target "$TEST_ROOT/claude" --agents claude --no-mcp
  ok_if "explicit non-Codex selection excludes Codex adapters" "$([[ ! -e "$TEST_ROOT/claude/.codex" && ! -e "$TEST_ROOT/claude/.agents/skills/avb-plan" ]] && echo true || echo false)"
}

test_existing_files() {
  local target="$TEST_ROOT/existing"
  mkdir -p "$target/.codex" "$target/xops/init"
  printf 'custom config\n' > "$target/.codex/config.toml"
  printf 'project installer\n' > "$target/install.sh"
  printf 'project setup\n' > "$target/xops/init/setup.sh"
  run_install --target "$target" --agents codex --no-mcp
  ok_if "existing Codex config is preserved" "$([[ $(< "$target/.codex/config.toml") == 'custom config' ]] && echo true || echo false)"
  ok_if "project installer and setup are preserved" "$([[ -f "$target/install.sh" && -f "$target/xops/init/setup.sh" ]] && echo true || echo false)"
  printf 'custom skill\n' > "$target/.agents/skills/avb-plan/SKILL.md"
  run_install --target "$target" --agents codex --no-mcp
  ok_if "existing prompt skill is preserved" "$([[ $(< "$target/.agents/skills/avb-plan/SKILL.md") == 'custom skill' ]] && echo true || echo false)"
  run_install --target "$target" --agents codex --no-mcp --force
  ok_if "force regenerates Codex config and adapter" "$(
    if grep -q 'approval_policy' "$target/.codex/config.toml" && grep -q 'name: avb-plan' "$target/.agents/skills/avb-plan/SKILL.md"; then echo true; else echo false; fi
  )"
}

test_quoted_paths_and_dryrun() {
  local target="$TEST_ROOT/space \"quote\" & pipe| back\\slash"
  run_install --target "$target" --agents codex --no-vscode
  local got=0
  python3 - "$target" <<'PY' || got=$?
import json
import sys
import tomllib
from pathlib import Path
target = Path(sys.argv[1])
config = tomllib.loads((target / '.codex/config.toml').read_text())
assert config['mcp_servers']['codegraph']['cwd'] == str(target)
assert config['mcp_servers']['codegraph']['args'][-1] == str(target)
assert json.loads((target / '.mcp.json').read_text())['mcpServers']['codegraph']['args'][-1] == str(target)
PY
  ok_if "MCP TOML and JSON round-trip special target characters" "$([[ $got -eq 0 ]] && echo true || echo false)"
  run_install --target "$TEST_ROOT/dry/new" --agents codex --dry-run
  ok_if "dry-run does not create even the target directory" "$([[ ! -e "$TEST_ROOT/dry" ]] && echo true || echo false)"
  ok_if "dry-run reports Codex output" "$(if grep -q '.codex/config.toml' "$TEST_ROOT/install.log"; then echo true; else echo false; fi)"
}

test_codex_tracking() {
  local target="$TEST_ROOT/project" got=0
  bash "$target/xops/agent/tracking_append.sh" --agent=codex --scope=smoke \
    --action=commit --status=completed --commit-sha=pending \
    --summary='test(codex): verify tracking integration' || got=$?
  ok_if "scaffolded tracking accepts Codex identity" "$([[ $got -eq 0 ]] && echo true || echo false)"
  local parsed=0
  python3 - "$target/docs/tracking/tracking.csv" <<'PY' || parsed=$?
import csv
import sys
with open(sys.argv[1], newline='') as stream:
    rows = list(csv.DictReader(stream))
assert len(rows) == 1
assert rows[0]['agent'] == 'codex'
assert rows[0]['commit_sha'] == 'pending'
PY
  ok_if "Codex completion produces a pending tracking row" "$([[ $parsed -eq 0 ]] && echo true || echo false)"
}

test_codex_install
test_native_formats
test_defaults_and_optouts
test_existing_files
test_quoted_paths_and_dryrun
test_codex_tracking
log_step "scaffold_codex: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
