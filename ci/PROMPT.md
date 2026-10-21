# 🚀 One-box prompt: add the GitHub CI/CD pipeline to a project

Paste everything below the line into your agent's chat box. Replace `<TARGET>` with the project path
(omit it to use the current workspace). This is optional and standalone; it is not part of
`install.sh` or `scaffold.sh`.

---

Install and adapt the GitHub CI/CD pipeline from `ci/` of the agentic-workspace template into the
project at `<TARGET>`, then prove it on GitHub.

1. Read `ci/AGENT_GUIDE.md` completely first, then follow its procedure exactly. Its invariants and
   token rules are non-negotiable.
2. Detect the project's context yourself (git remote and default branch, language and lockfiles,
   existing `.github/`, version file, changelog, Dockerfile, hosting). Then ask me, in one form, only
   what you cannot infer:
   - the production approver's GitHub login;
   - whether to publish a container image (GHCR);
   - whether to deploy a website, and if so **which existing GitHub repository receives it**
     (for example `owner/site`) or this repo's own Pages. That repository must already exist with its
     branch; the pipeline never creates it and never publishes anywhere else;
   - a **temporary** GitHub token for setup and initial tests (fine-grained, limited to this repo,
     short expiry; I will revoke it) and, for a site repo, a second token limited to that repo with
     contents:write, which becomes the `production` environment secret.
3. Write `<TARGET>/.github/cicd.json` (schema: `ci/cicd.example.json`), run
   `python3 ci/apply.py --target <TARGET> --dry-run`, review, then run it for real.
4. Run `python3 ci/preflight.py --target <TARGET>` with the token only as the `GH_TOKEN` environment
   variable of that command. Stop and tell me if the source repo, `develop`, the site repo or its
   branch is missing, or the approver id is wrong.
5. Adapt what the generator cannot know: real stack commands in `ci.mk`, `-include ci.mk` in the
   Makefile, version file and changelog, Dockerfile base digest; remove what does not apply.
6. Prove locally: `python3 ci/check.py --target <TARGET>`, the generated `test/tool` tests and the
   project's own `make verify`. Fix root causes; never weaken a check.
7. Show me `python3 ci/settings.py --target <TARGET>` (dry run), then apply it with the token
   (`--apply`, plus `--site-token-env <VAR>` for the site secret).
8. Initial tests, within these limits only: push one branch `<agent>/feature/ci-pipeline`, open a PR
   into `develop`, watch Branch policy, Verify and Security, fix failures from the logs. After I merge,
   dispatch the release workflow with an **empty version** (artifacts only). Never merge, never push
   `main`/`develop`, never dispatch a real version. If the project's rules forbid agent commits or
   pushes, stop after step 7 and hand over.
9. Never print, log, write, commit or echo a token. Finish by unsetting it, reminding me to revoke it,
   following the project's tracking/staging rules, and reporting files created, check results and my
   remaining manual steps (approving the first release).
