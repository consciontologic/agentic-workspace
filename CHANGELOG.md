# Changelog

## [Unreleased]

### Added

- Optional standalone `ci/` kit (not wired into `install.sh`/`scaffold.sh`): a one-box prompt,
  agent guide, renderer, validator and GitHub-settings script that generate a gitflow +
  SemVer release + GHCR/Pages deployment pipeline with grouped CI logging, modelled on the
  wfform and worthhit repositories.
- Codex is included by default and selectable with `--agents codex`: native
  project configuration, four adapted agent roles, explicit prompt skills,
  shared instructions and CodeGraph MCP for local ChatGPT desktop / Codex use.
- Codex agent identity is accepted in completion tracking rows.

### Changed

- Copilot slash commands migrated from `.github/prompts/*.prompt.md` to skills under
  `.agents/skills/<name>/` (the single skill location, user-invoked only; Codex gets
  `agents/openai.yaml` with implicit invocation disabled). The separate Codex `avb-*`
  adapters and the `.github/prompts` install step were removed; the old `/self-review`
  wrapper was dropped in favour of the existing `self-review` skill. Links in skills and
  agents were corrected, and tests and docs follow the new layout.
- Repository and framework renamed from `ai-vscode-basics` to `agentic-workspace`.
  All URLs, cache paths, documentation, scripts and the version stamp file now
  use the new name.
- Scaffolding requires Python 3.9+ and includes complete skill resource trees.
- Framework-only installer files are excluded when copying, rather than deleted
  from the target after installation; existing project setup files survive.

### Fixed

- Codex MCP configuration now preserves CodeGraph environment settings.
- Shared agent rules preserve unrelated work on failed gates and allow local
  exploration when CodeGraph is unavailable or disabled.
- Skill descriptions and broken resource links are repaired; roadmap guidance
  uses available editing tools and repository-local checkpoints.

- `make git` no longer creates empty commits: all pending tracking rows in a
  staging window now ride one real commit (first pending summary as the
  subject, the rest under "Also includes:", one `[run_id]` trailer each), and
  with a clean tree the rows simply wait for the next real commit instead of
  committing empty markers.
- Dry-run no longer creates a missing target directory.
- Generated MCP JSON and TOML preserve paths containing quotes and backslashes.
