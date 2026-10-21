"""Enforce gitflow branch naming and PR direction from .github/gitflow.json.

Usage: HEAD_REF=<head> BASE_REF=<base> python3 tool/gitflow_check.py
"""
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SEMVER = r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)'
SLUG = r'[a-z0-9][a-z0-9._-]*'


def check(head, base, policy):
    production, integration = policy['production'], policy['integration']
    if head == integration and base == production:
        return 'promotion'
    if head.startswith('dependabot/'):
        if base != integration:
            raise ValueError(f'Dependency updates must target {integration}.')
        return 'dependencies'
    agents = '|'.join(re.escape(a) for a in policy['agent_prefixes'])
    match = re.fullmatch(rf'(?:(?:{agents})/)?(feature|bugfix|hotfix|release)/(.+)', head)
    if not match:
        raise ValueError(
            f'Branch "{head}" must be [agent/]feature|bugfix|hotfix/<slug> or release/MAJOR.MINOR.PATCH.')
    kind, name = match.groups()
    rule = policy['branches'][kind]
    if kind == 'release':
        if not re.fullmatch(SEMVER, name):
            raise ValueError('Release branches must be named release/MAJOR.MINOR.PATCH.')
    elif not re.fullmatch(SLUG, name):
        raise ValueError(f'Branch slug "{name}" must be lowercase letters, digits, dots, dashes or underscores.')
    if base != rule['pull_request_into']:
        raise ValueError(f'{kind} branches must open pull requests into {rule["pull_request_into"]}, not {base}.')
    return kind


def main():
    policy = json.loads((ROOT / '.github/gitflow.json').read_text())
    head, base = os.environ.get('HEAD_REF', ''), os.environ.get('BASE_REF', '')
    try:
        print(f'Gitflow OK: {head} -> {base} ({check(head, base, policy)})')
    except ValueError as error:
        print(f'Gitflow violation: {error}', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
