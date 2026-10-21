#!/usr/bin/env python3
"""Validate a project that ci/apply.py rendered. Exit 1 on errors, 0 otherwise.

Usage: python3 ci/check.py --target /path/to/project
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply as renderer  # noqa: E402

USES = re.compile(r'^\s*-?\s*uses:\s*(\S+)', re.M)
LEFTOVER = re.compile(r'(?<!\$)\{\{[A-Za-z_:/.\-]+\}\}')
SEMVER = r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)'


def check(target):
    """Return (errors, warnings)."""
    errors, notes = [], []
    config_path = target / '.github/cicd.json'
    try:
        cfg = renderer.resolve(json.loads(config_path.read_text()))
    except (OSError, json.JSONDecodeError, renderer.ConfigError) as error:
        return [f'.github/cicd.json: {error}'], notes
    notes.extend(renderer.warnings(cfg))
    expected = {dest: content for dest, content, _, policy in renderer.plan(cfg) if policy != 'seed'}
    for destination, content in expected.items():
        path = target / destination
        if not path.is_file():
            errors.append(f'{destination}: missing (run ci/apply.py)')
            continue
        text = path.read_text()
        if LEFTOVER.search(text):
            errors.append(f'{destination}: unresolved placeholder')
        if text != content and destination != '.github/cicd.json':
            notes.append(f'{destination}: differs from the template output (hand edits or stale render)')
    workflow = target / '.github/workflows/ci.yml'
    if workflow.is_file():
        names = set(re.findall(r'^\s+name:\s*(.+?)\s*$', workflow.read_text(), re.M))
        for check_name in cfg['required_checks']:
            if check_name not in names:
                errors.append(f'required check "{check_name}" has no job with that name in ci.yml')
    for path in (target / '.github/workflows').glob('*.yml'):
        for ref in USES.findall(path.read_text()):
            if not ref.startswith('./') and not re.fullmatch(r'[^@\s]+@[0-9a-f]{40}', ref):
                errors.append(f'{path.name}: action {ref} is not pinned to a full commit SHA')
    version_file = target / cfg['version_file']
    if not version_file.is_file():
        errors.append(f'{cfg["version_file"]}: version source is missing')
    else:
        match = re.search(cfg['version_regex'], version_file.read_text(), re.M)
        if not match or not re.fullmatch(SEMVER, match.group('v')):
            errors.append(f'{cfg["version_file"]}: no plain MAJOR.MINOR.PATCH version found')
        else:
            changelog = target / cfg['changelog']
            heading = rf'^## \[{re.escape(match.group("v"))}\] - \d{{4}}-\d{{2}}-\d{{2}}$'
            if not changelog.is_file() or not re.search(heading, changelog.read_text(), re.M):
                notes.append(f'{cfg["changelog"]} has no dated entry for {match.group("v")} (needed before releasing)')
    makefile = target / 'Makefile'
    if not makefile.is_file() or not re.search(r'^-?include\s+ci\.mk', makefile.read_text(), re.M):
        notes.append('Makefile does not include ci.mk; add "-include ci.mk" so CI targets exist')
    if cfg['features']['container'] and not (target / cfg['container']['dockerfile']).is_file():
        errors.append(f'{cfg["container"]["dockerfile"]}: container feature enabled but file is missing')
    return errors, notes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    errors, notes = check(args.target.resolve())
    for note in notes:
        print(f'⚠️  {note}', file=sys.stderr)
    for error in errors:
        print(f'❌ {error}', file=sys.stderr)
    print('✅ CI/CD pipeline is consistent.' if not errors else f'❌ {len(errors)} problem(s).', file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
