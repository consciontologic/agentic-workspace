# {{PROJECT}} release and deployment

Releases are published only by the **📦 Packages and release** workflow, dispatched manually on `{{PRODUCTION}}`.

1. Prepare on `{{INTEGRATION}}`: bump `{{VERSION_FILE}}`, date the `{{CHANGELOG}}` entry, merge via PR.
2. Promote `{{INTEGRATION}}` to `{{PRODUCTION}}` through a PR (exact tested tree, no new content).
3. Dispatch the workflow with `version` = the plain SemVer. An empty version builds artifacts only.
4. `build` verifies the version, changelog, promoted source and prior validation, builds **once** and uploads `{{PROJECT}}-release-<sha>`.
5. `publish` waits in the **production** environment for {{REVIEWER}}'s approval, re-verifies the approval receipt and
   source, verifies the exact approved bytes, then publishes: {{PUBLISH_STEPS}}.

Guarantees: tags, release assets and package versions are immutable; an existing conflicting tag, asset or image fails the run;
nothing is retried automatically; approval is never bypassed.

## Required live GitHub settings (policy files do not apply them)

Run `python3 ci/settings.py --repo {{REPOSITORY}}` (dry run) and review, or add `--apply`.

- Branch protection on `{{PRODUCTION}}` and `{{INTEGRATION}}`: PR required, checks {{REQUIRED_CHECKS}}, conversations resolved, no force push.
- Environment `production`: required reviewer {{REVIEWER}}, deployment branches limited to `{{PRODUCTION}}`.
{{SECRET_NOTES}}
## Recovery

Read the failed run's log first. Partial releases stay drafts and resume only for the same source; never delete or move a published tag.
