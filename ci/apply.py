#!/usr/bin/env python3
"""Render the GitHub CI/CD pipeline (gitflow, SemVer releases, packages, deployments) into a project.

Usage:
  python3 ci/apply.py --target /path/to/project [--config FILE] [--dry-run] [--force]
  python3 ci/apply.py --refresh-pins

The config defaults to <target>/.github/cicd.json (see ci/cicd.example.json). This script
is standalone: it is deliberately not wired into install.sh or scaffold.sh.
"""
import argparse
import copy
from datetime import date
import json
import os
from pathlib import Path
import re
import stat
import sys
import urllib.request

CI = Path(__file__).resolve().parent
TEMPLATES = CI / 'templates'
PLACEHOLDER = re.compile(r'\{\{([A-Za-z_:/.\-]+)\}\}')
BRANCH = re.compile(r'[A-Za-z0-9][A-Za-z0-9._/-]*')
SLUG = re.compile(r'[a-z0-9][a-z0-9-]*')
STACKS = sorted(p.stem for p in (CI / 'stacks').glob('*.json'))

DEFAULTS = {
    'production_branch': 'main',
    'integration_branch': 'develop',
    'agent_prefixes': ['codex', 'claude', 'copilot'],
    'tag_prefix': '',
    'changelog': 'CHANGELOG.md',
    'features': {'container': False, 'pages': False, 'pages_repo': False},
    'container': {'context': '.', 'dockerfile': 'Dockerfile', 'smoke_port': 8080, 'smoke_path': '/'},
    'pages': {},
    'pages_repo': {'branch': 'main', 'subdir': '', 'secret': 'DEPLOY_TOKEN'},
    'production_reviewer': {'login': '', 'id': 0},
    'required_checks': ['Branch policy', 'Verify', 'Security'],
    'required_jobs': ['Verify', 'Security'],
}

# (template, destination, feature required or None, policy)
# managed: rewritten with --force; seed: created once and never overwritten.
FILES = [
    ('.github/release.yml', '.github/release.yml', None, 'managed'),
    ('.github/dependabot.yml', '.github/dependabot.yml', None, 'managed'),
    ('.github/workflows/ci.yml', '.github/workflows/ci.yml', None, 'managed'),
    ('.github/workflows/release.yml', '.github/workflows/release.yml', None, 'managed'),
    ('tool/ci-step.sh', 'tool/ci-step.sh', None, 'managed'),
    ('tool/release.py', 'tool/release.py', None, 'managed'),
    ('tool/release_guard.py', 'tool/release_guard.py', None, 'managed'),
    ('tool/gitflow_check.py', 'tool/gitflow_check.py', None, 'managed'),
    ('tool/repo_check.py', 'tool/repo_check.py', None, 'managed'),
    ('tool/container.py', 'tool/container.py', 'container', 'managed'),
    ('tool/publish_website.py', 'tool/publish_website.py', 'pages_repo', 'managed'),
    ('test/tool/test_release_tools.py', 'test/tool/test_release_tools.py', None, 'managed'),
    ('docs/GITFLOW.md', 'docs/GITFLOW.md', None, 'managed'),
    ('docs/DEPLOYMENT.md', 'docs/DEPLOYMENT.md', None, 'managed'),
    ('ci.mk', 'ci.mk', None, 'managed'),
    ('CHANGELOG.md', 'CHANGELOG.md', None, 'seed'),
    ('Dockerfile', 'Dockerfile', 'container', 'seed'),
]


class ConfigError(ValueError):
    pass


def log(icon, message):
    print(f'{icon} {message}', file=sys.stderr)


def deep_merge(base, over):
    merged = copy.deepcopy(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_stack(name):
    path = CI / 'stacks' / f'{name}.json'
    if not path.is_file():
        raise ConfigError(f'Unknown stack "{name}"; choose one of: {", ".join(STACKS)}.')
    return json.loads(path.read_text())


def resolve(raw):
    for key in ('repository', 'stack'):
        if not raw.get(key):
            raise ConfigError(f'"{key}" is required.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', raw['repository']):
        raise ConfigError('"repository" must look like OWNER/REPO.')
    owner, repo = raw['repository'].split('/')
    stack = load_stack(raw['stack'])
    cfg = deep_merge(DEFAULTS, {k: v for k, v in stack.items() if k not in ('setup_steps', 'dependabot_ecosystem')})
    cfg = deep_merge(cfg, {k: v for k, v in raw.items() if not k.startswith('$') and not k.startswith('_')})
    cfg.setdefault('project', repo.lower())
    cfg['container'].setdefault('image', f'ghcr.io/{owner.lower()}/{repo.lower()}')
    cfg['dependabot_ecosystem'] = stack.get('dependabot_ecosystem')
    validate(cfg)
    return cfg


def validate(cfg):
    if not SLUG.fullmatch(cfg['project']):
        raise ConfigError('"project" must be a lowercase slug (letters, digits, dashes).')
    for key in ('production_branch', 'integration_branch'):
        if not BRANCH.fullmatch(cfg[key]):
            raise ConfigError(f'"{key}" is not a valid branch name.')
    if cfg['production_branch'] == cfg['integration_branch']:
        raise ConfigError('Production and integration branches must differ.')
    if not all(re.fullmatch(r'[a-z][a-z0-9-]*', a) for a in cfg['agent_prefixes']):
        raise ConfigError('"agent_prefixes" must be lowercase slugs.')
    if not re.fullmatch(r'[A-Za-z0-9._-]*', cfg['tag_prefix']):
        raise ConfigError('"tag_prefix" may contain only letters, digits, dots, dashes and underscores.')
    for key, value in cfg['commands'].items():
        if not isinstance(value, str) or not value.strip() or '\n' in value or '{{' in value:
            raise ConfigError(f'commands.{key} must be one non-empty line without "{{{{".')
    for key in ('deps', 'verify', 'build', 'security'):
        if key not in cfg['commands']:
            raise ConfigError(f'commands.{key} is required.')
    for key in ('version_file', 'version_regex', 'artifact_dir', 'changelog'):
        if not cfg.get(key):
            raise ConfigError(f'"{key}" is required.')
    re.compile(cfg['version_regex'])
    if '(?P<v>' not in cfg['version_regex']:
        raise ConfigError('"version_regex" needs a (?P<v>...) group.')
    for key in ('version_file', 'artifact_dir', 'changelog'):
        if cfg[key].startswith('/') or '..' in Path(cfg[key]).parts:
            raise ConfigError(f'"{key}" must be a relative path inside the repository.')
    features = cfg['features']
    if features['pages'] and features['pages_repo']:
        raise ConfigError('Enable only one of features.pages (same repo) and features.pages_repo (separate repo).')
    if features['container'] and not re.fullmatch(r'[a-z0-9][a-z0-9._/-]*', cfg['container']['image']):
        raise ConfigError('container.image must be lowercase.')
    if features['pages_repo']:
        settings = cfg['pages_repo']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', settings.get('repository', '')):
            raise ConfigError('pages_repo.repository must look like OWNER/REPO.')
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', settings['secret']):
            raise ConfigError('pages_repo.secret must be an UPPER_SNAKE secret name.')
    if not isinstance(cfg['production_reviewer']['id'], int):
        raise ConfigError('production_reviewer.id must be an integer GitHub user id.')


def warnings(cfg):
    found = []
    if not cfg['production_reviewer']['login'] or not cfg['production_reviewer']['id']:
        found.append('production_reviewer is not set; releases cannot be approved until login and numeric id '
                     'are filled in (gh api users/<login> --jq .id).')
    return found


def load_pins():
    return json.loads((CI / 'pins.json').read_text())


def pin(name, pins):
    entry = pins.get(name)
    if not entry or not re.fullmatch(r'[0-9a-f]{40}', entry.get('sha', '')):
        raise ConfigError(f'No pinned SHA for action {name}; run: python3 ci/apply.py --refresh-pins')
    return f'{name}@{entry["sha"]} # {entry["tag"]}'


def flags_for(cfg):
    return {**cfg['features'], 'ecosystem': bool(cfg['dependabot_ecosystem'])}


def variables(cfg):
    prod, integ = cfg['production_branch'], cfg['integration_branch']
    hotfix = ['hotfix/'] + [f'{a}/hotfix/' for a in cfg['agent_prefixes']]
    starts = ' || '.join(f"startsWith(github.head_ref, '{p}')" for p in hotfix)
    features = cfg['features']
    publish = []
    if features['container']:
        publish.append('immutable GHCR image')
    if features['pages_repo']:
        publish.append(f'website repository {cfg["pages_repo"]["repository"]} (GitOps)')
    if features['pages']:
        publish.append('GitHub Pages (separate `pages` job)')
    publish.append('SemVer tag and immutable GitHub release assets')
    notes = []
    if features['pages_repo']:
        notes.append(f'- Environment secret `{cfg["pages_repo"]["secret"]}` in `production`: a fine-grained token '
                     f'with contents:write on {cfg["pages_repo"]["repository"]} only.')
    if features['pages']:
        notes.append('- Settings > Pages > Source: GitHub Actions.')
    if features['container']:
        notes.append('- Package visibility/permissions for the GHCR image match the repository.')
    if features['pages']:
        site = cfg['pages'].get('url', f'https://github.com/{cfg["repository"]}')
    elif features['pages_repo']:
        site = cfg['pages_repo'].get('url', f'https://github.com/{cfg["pages_repo"]["repository"]}')
    else:
        site = f'https://github.com/{cfg["repository"]}/releases'
    reviewer = cfg['production_reviewer']['login']
    return {
        'PROJECT': cfg['project'], 'REPOSITORY': cfg['repository'], 'PRODUCTION': prod, 'INTEGRATION': integ,
        'GATE': f"github.base_ref == '{integ}' || (github.base_ref == '{prod}' && ({starts}))",
        'TAG_PREFIX_EXAMPLE': f'{cfg["tag_prefix"]}MAJOR.MINOR.PATCH', 'CHANGELOG': cfg['changelog'],
        'VERSION_FILE': cfg['version_file'], 'ARTIFACT_DIR': cfg['artifact_dir'],
        'AGENTS_LIST': ', '.join(f'`{a}`' for a in cfg['agent_prefixes']) or 'none',
        'AGENTS_EXAMPLE': (cfg['agent_prefixes'] or ['agent'])[0],
        'REQUIRED_CHECKS': ', '.join(f'`{c}`' for c in cfg['required_checks']),
        'REVIEWER': f'@{reviewer}' if reviewer else 'the configured reviewer',
        'PUBLISH_STEPS': '; '.join(publish), 'SECRET_NOTES': '\n'.join(notes) + ('\n' if notes else ''),
        'SITE_URL': site, 'PAGES_SECRET': cfg['pages_repo']['secret'], 'ECOSYSTEM': cfg['dependabot_ecosystem'] or '',
        'IMAGE_TARGETS': ' image image.test' if features['container'] else '',
        'CMD_DEPS': cfg['commands']['deps'], 'CMD_VERIFY': cfg['commands']['verify'],
        'CMD_BUILD': cfg['commands']['build'], 'CMD_SECURITY': cfg['commands']['security'],
        'TODAY': os.environ.get('CICD_TODAY') or date.today().isoformat(),
    }


def render(text, flags, values, pins, setup_steps):
    lines, active = [], [True]
    for line in text.splitlines():
        directive = line.strip()
        if directive.startswith('#@if '):
            name = directive[5:].strip()
            negate = name.startswith('!')
            name = name.lstrip('!')
            if name not in flags:
                raise ConfigError(f'Unknown template flag "{name}".')
            active.append(active[-1] and (flags[name] != negate))
        elif directive == '#@endif':
            active.pop()
        elif active[-1]:
            if directive == '{{SETUP_STEPS}}':
                indent = line[:len(line) - len(line.lstrip())]
                lines.extend(indent + step for step in setup_steps)
            else:
                lines.append(line)
    if len(active) != 1:
        raise ConfigError('Unbalanced #@if/#@endif in template.')

    def substitute(match):
        key = match.group(1)
        if key.startswith('PIN:'):
            return pin(key[4:], pins)
        if key not in values:
            raise ConfigError(f'Unknown template placeholder {{{{{key}}}}}.')
        return str(values[key])
    return PLACEHOLDER.sub(substitute, '\n'.join(lines) + '\n')


def gitflow_policy(cfg):
    prod, integ = cfg['production_branch'], cfg['integration_branch']
    return {
        'production': prod, 'integration': integ,
        'branches': {
            'feature': {'from': integ, 'pull_request_into': integ},
            'bugfix': {'from': integ, 'pull_request_into': integ},
            'hotfix': {'from': prod, 'pull_request_into': prod, 'back_merge_into': integ},
            'release': {'from': integ, 'pull_request_into': integ, 'promote_from': integ, 'promote_into': prod},
        },
        'agent_prefixes': cfg['agent_prefixes'], 'semver': 'MAJOR.MINOR.PATCH', 'tag_prefix': cfg['tag_prefix'],
        'required_checks': cfg['required_checks'], 'require_pull_request': True, 'require_review': False,
        'required_approving_review_count': 0, 'require_conversation_resolution': True, 'force_push': False,
        'publication_environment': 'production', 'publication_trigger': 'workflow_dispatch_on_' + prod,
        'overwrite_existing_release_assets': False,
        'note': 'Policy description only; apply it to GitHub with ci/settings.py.',
    }


def as_json(value):
    return json.dumps(value, indent=2) + '\n'


def plan(cfg):
    """Return [(destination, content, executable, policy)]."""
    stack = load_stack(cfg['stack'])
    flags, values, pins = flags_for(cfg), variables(cfg), load_pins()
    outputs = [('.github/gitflow.json', as_json(gitflow_policy(cfg)), False, 'managed'),
               ('.github/cicd.json', as_json({k: v for k, v in cfg.items() if k != 'dependabot_ecosystem'}),
                False, 'config')]
    for source, destination, feature, policy in FILES:
        if feature and not cfg['features'][feature]:
            continue
        text = (TEMPLATES / source).read_text()
        outputs.append((destination, render(text, flags, values, pins, stack['setup_steps']),
                        source.endswith('.sh'), policy))
    return outputs


def apply(target, cfg, config_path=None, dry_run=False, force=False):
    results = []
    for destination, content, executable, policy in plan(cfg):
        path = target / destination
        if not path.exists():
            status = 'create'
        elif path.read_text() == content:
            status = 'unchanged'
        elif policy == 'seed':
            status = 'skip (exists; seed files are never overwritten)'
        elif policy == 'config' and config_path is not None and path.resolve() == config_path.resolve():
            status = 'update'
        elif force:
            status = 'update'
        else:
            status = 'skip (differs; re-run with --force to overwrite)'
        results.append((destination, status))
        if status in ('create', 'update') and not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            if executable:
                path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return results


def refresh_pins():
    pins = load_pins()
    headers = {'User-Agent': 'agentic-workspace-ci', 'Accept': 'application/vnd.github+json'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']

    def get(path):
        with urllib.request.urlopen(urllib.request.Request('https://api.github.com' + path, headers=headers),
                                    timeout=30) as response:
            return json.load(response)
    for name, entry in pins.items():
        if name.startswith('_'):
            continue
        tag = get(f'/repos/{name}/releases/latest')['tag_name']
        obj = get(f'/repos/{name}/git/ref/tags/{tag}')['object']
        if obj['type'] == 'tag':
            obj = get(f'/repos/{name}/git/tags/{obj["sha"]}')['object']
        entry.update(tag=tag, sha=obj['sha'])
        log('📌', f'{name} -> {tag} {obj["sha"][:12]}')
    (CI / 'pins.json').write_text(json.dumps(pins, indent=2) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--target', type=Path, default=Path.cwd())
    parser.add_argument('--config', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--refresh-pins', action='store_true')
    args = parser.parse_args(argv)
    if args.refresh_pins:
        refresh_pins()
        return 0
    target = args.target.resolve()
    config_path = args.config or target / '.github/cicd.json'
    try:
        cfg = resolve(json.loads(config_path.read_text()))
        results = apply(target, cfg, config_path, args.dry_run, args.force)
    except (ConfigError, FileNotFoundError, json.JSONDecodeError) as error:
        log('❌', f'{type(error).__name__}: {error}')
        return 2
    for destination, status in results:
        log('ℹ️ ', f'{status:<10} {destination}')
    for message in warnings(cfg):
        log('⚠️ ', message)
    log('✅', ('Dry run complete.' if args.dry_run else 'Pipeline rendered.') +
        ' Next: python3 ci/check.py --target ' + str(target))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
