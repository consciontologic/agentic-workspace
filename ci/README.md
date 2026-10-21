# ci/ — optional GitHub CI/CD pipeline generator

A standalone kit that renders the delivery model of `wfform` / `worthhit` (gitflow, SemVer releases,
GHCR packages, GitHub Pages deployment, human-approved publication, grouped CI logging) into any
project hosted on GitHub. It is **not** wired into `install.sh` or `scaffold.sh`.

## Use it from one chat box

Paste [`PROMPT.md`](PROMPT.md) into your agent. It reads [`AGENT_GUIDE.md`](AGENT_GUIDE.md),
detects the project's context, writes `.github/cicd.json`, renders, adapts and verifies.

## Or run it by hand

```bash
cp ci/cicd.example.json /path/to/project/.github/cicd.json   # edit repository, stack, features
python3 ci/apply.py --target /path/to/project --dry-run       # review the plan
python3 ci/apply.py --target /path/to/project
python3 ci/check.py --target /path/to/project                 # consistency gate
GH_TOKEN=... python3 ci/preflight.py --target /path/to/project  # repos/branches/approver exist? (read-only)
python3 ci/settings.py --target /path/to/project              # dry run of live GitHub settings
```

The deployment repository (`pages_repo.repository`) must already exist; the pipeline only pushes to
it, and nowhere else. The prompt asks for a temporary, narrowly scoped token so the agent can run
preflight, apply settings and run the first checks; see the token rules in `AGENT_GUIDE.md`.

## Layout

| Path | Purpose |
|---|---|
| `PROMPT.md` | the single-chatbox prompt |
| `AGENT_GUIDE.md` | procedure, detect-vs-ask table, invariants, config reference |
| `apply.py`, `check.py`, `preflight.py`, `settings.py` | renderer, validator, GitHub existence checks, GitHub settings (dry run by default) |
| `cicd.example.json`, `stacks/`, `pins.json` | config example, stack presets, SHA-pinned actions |
| `templates/` | workflows, release/guard/container/website tools, docs, Make contract |
| `tests/` | `python3 -m unittest discover -s ci/tests` (also run by `bash xops/test/run_tests.sh`) |

Requires Python 3.9+ and, for `settings.py --apply` only, an authenticated `gh`.
