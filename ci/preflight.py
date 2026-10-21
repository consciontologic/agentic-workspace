#!/usr/bin/env python3
"""Read-only preflight: verify the GitHub side exists before (or after) rendering the pipeline.

Needs a token for private repositories and for permission checks; pass it only through the
environment (GH_TOKEN or GITHUB_TOKEN). The token is never printed or written anywhere.

Checks: the source repo, its production/integration branches, the site repository and branch when
features.pages_repo is on (it must already exist and be pushable by the token), and that
production_reviewer.id matches the login. Exit 1 on errors.

Usage: GH_TOKEN=... python3 ci/preflight.py --target /path/to/project
"""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply as renderer  # noqa: E402


def token():
    return os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')


def get(path):
    """GET from the GitHub API; returns None on 404."""
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'agentic-workspace-ci',
               'X-GitHub-Api-Version': '2022-11-28'}
    if token():
        headers['Authorization'] = 'Bearer ' + token()
    try:
        with urllib.request.urlopen(urllib.request.Request('https://api.github.com' + path, headers=headers),
                                    timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (404, 401, 403):
            return None
        raise


def preflight(cfg, api=get):
    """Return (errors, notes)."""
    errors, notes = [], []
    repo = cfg['repository']
    info = api(f'/repos/{repo}')
    if info is None:
        return [f'{repo}: not found or not visible to this token. Create it (or fix the token scope) first.'], notes
    permissions = info.get('permissions') or {}
    if token() and not permissions.get('admin'):
        notes.append(f'{repo}: token lacks admin; ci/settings.py --apply (branch protection, environments) will fail.')
    for key in ('production_branch', 'integration_branch'):
        branch = cfg[key]
        if api(f'/repos/{repo}/branches/{urllib.parse.quote(branch, safe="")}') is None:
            errors.append(f'{repo}: branch "{branch}" does not exist yet; create it before enabling protection.')
    if cfg['features']['pages_repo']:
        site = cfg['pages_repo']
        site_info = api(f'/repos/{site["repository"]}')
        if site_info is None:
            errors.append(f'{site["repository"]}: deployment repository does not exist or is not visible. '
                          'Create it first; the pipeline never creates it.')
        else:
            if api(f'/repos/{site["repository"]}/branches/{urllib.parse.quote(site["branch"], safe="")}') is None:
                errors.append(f'{site["repository"]}: branch "{site["branch"]}" does not exist; push an initial commit.')
            if token() and not (site_info.get('permissions') or {}).get('push'):
                errors.append(f'{site["repository"]}: this token cannot push; the deploy secret needs its own '
                              'token with contents:write on that repository.')
    if cfg['features']['pages'] and not info.get('has_pages') and not cfg['pages'].get('url'):
        notes.append('Pages is not enabled yet: Settings > Pages > Source: GitHub Actions.')
    reviewer = cfg['production_reviewer']
    if reviewer['login']:
        user = api('/users/' + urllib.parse.quote(reviewer['login'], safe=''))
        if user is None:
            errors.append(f'production_reviewer.login "{reviewer["login"]}" does not exist.')
        elif user.get('id') != reviewer['id']:
            errors.append(f'production_reviewer.id should be {user.get("id")} for {reviewer["login"]}.')
    else:
        errors.append('production_reviewer.login is not set; ask the user who approves releases.')
    return errors, notes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--target', type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        cfg = renderer.resolve(json.loads((args.target / '.github/cicd.json').read_text()))
        errors, notes = preflight(cfg)
    except (OSError, json.JSONDecodeError, renderer.ConfigError, urllib.error.URLError) as error:
        print(f'❌ {type(error).__name__}: {error}', file=sys.stderr)
        return 2
    if not token():
        notes.append('No GH_TOKEN/GITHUB_TOKEN set: private repositories and permissions cannot be verified.')
    for note in notes:
        print(f'⚠️  {note}', file=sys.stderr)
    for error in errors:
        print(f'❌ {error}', file=sys.stderr)
    print('✅ GitHub preflight passed.' if not errors else f'❌ {len(errors)} problem(s).', file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
