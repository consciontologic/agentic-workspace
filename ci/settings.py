#!/usr/bin/env python3
"""Apply the live GitHub settings the pipeline relies on (branch protection, production environment).

Dry run by default: prints the exact API calls. Nothing changes until --apply, which needs an
authenticated `gh` with admin rights. Policy files in the repo do not configure GitHub by themselves.

With --site-token-env NAME the deploy secret (pages_repo.secret) is stored in the production
environment from that environment variable, passed to gh via stdin and never printed.

Usage: python3 ci/settings.py --target /path/to/project [--apply] [--site-token-env NAME]
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply as renderer  # noqa: E402


def calls(cfg):
    """Return [(method, path, payload)] for the settings."""
    repo = cfg['repository']
    result = []
    for branch in (cfg['production_branch'], cfg['integration_branch']):
        result.append(('PUT', f'/repos/{repo}/branches/{branch}/protection', {
            'required_status_checks': {'strict': True, 'contexts': cfg['required_checks']},
            'enforce_admins': True,
            'required_pull_request_reviews': {'required_approving_review_count': 0},
            'restrictions': None,
            'allow_force_pushes': False,
            'allow_deletions': False,
            'required_conversation_resolution': True,
        }))
    reviewer = cfg['production_reviewer']
    if not (reviewer['login'] and reviewer['id']):
        raise renderer.ConfigError('production_reviewer.login and .id are required for the production environment.')
    result.append(('PUT', f'/repos/{repo}/environments/production', {
        'reviewers': [{'type': 'User', 'id': reviewer['id']}],
        'prevent_self_review': False,
        'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True},
    }))
    result.append(('POST', f'/repos/{repo}/environments/production/deployment-branch-policies',
                   {'name': cfg['production_branch'], 'type': 'branch'}))
    return result


def secret_command(cfg):
    """gh command that stores the site deploy token as a production environment secret."""
    if not cfg['features']['pages_repo']:
        raise renderer.ConfigError('features.pages_repo is off; there is no deploy secret to set.')
    return ['gh', 'secret', 'set', cfg['pages_repo']['secret'], '--env', 'production', '--repo', cfg['repository']]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=Path.cwd())
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--site-token-env', help='name of the env var holding the site deploy token')
    args = parser.parse_args(argv)
    try:
        cfg = renderer.resolve(json.loads((args.target / '.github/cicd.json').read_text()))
        planned = calls(cfg)
    except (OSError, json.JSONDecodeError, renderer.ConfigError) as error:
        print(f'❌ {error}', file=sys.stderr)
        return 2
    for method, path, payload in planned:
        print(f'▶ {method} {path}\n{json.dumps(payload, indent=2)}')
        if args.apply:
            subprocess.run(['gh', 'api', '--method', method, path, '--input', '-'],
                           input=json.dumps(payload), text=True, check=True)
    if args.site_token_env:
        try:
            command = secret_command(cfg)
            value = os.environ.get(args.site_token_env, '')
            if args.apply and not value:
                raise renderer.ConfigError(f'${args.site_token_env} is empty.')
        except renderer.ConfigError as error:
            print(f'❌ {error}', file=sys.stderr)
            return 2
        print('▶ ' + ' '.join(command) + '  (value from $' + args.site_token_env + ')')
        if args.apply:
            subprocess.run(command, input=value, text=True, check=True)
    print('✅ Applied.' if args.apply else 'ℹ️  Dry run only; re-run with --apply to change GitHub.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
