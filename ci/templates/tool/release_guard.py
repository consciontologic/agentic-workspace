"""Read-only release authorization. Never submits or bypasses approvals."""
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release import CONFIG, REPOSITORY, SEMVER, release_notes, release_version  # noqa: E402

OWNER_ID = CONFIG['production_reviewer']['id']
PRODUCTION = CONFIG['production_branch']
INTEGRATION = CONFIG['integration_branch']
REQUIRED_JOBS = CONFIG['required_jobs']
SHA = re.compile(r'[0-9a-f]{40}')


def get(path):
    request = urllib.request.Request(
        'https://api.github.com' + path,
        headers={
            'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def release_request(api, sha, tree, root=Path(__file__).resolve().parents[1]):
    version = os.environ.get('RELEASE_VERSION', '')
    require(re.fullmatch(SEMVER, version), 'Enter a plain MAJOR.MINOR.PATCH version.')
    require(version == release_version(root), 'Requested version differs from the version file.')
    release_notes(version, root)
    require(SHA.fullmatch(sha), 'Release source must be an immutable commit.')
    base = '/repos/' + REPOSITORY
    develop = api(base + '/commits/' + INTEGRATION) or {}
    develop_sha = develop.get('sha', '')
    develop_tree = develop.get('commit', {}).get('tree', {}).get('sha', '')
    require(SHA.fullmatch(develop_sha) and SHA.fullmatch(develop_tree), 'Cannot verify integration source.')
    comparison = api(base + f'/compare/{sha}...{develop_sha}') or {}
    ahead = comparison.get('ahead_by')
    require(type(ahead) is int and ahead >= 0, 'Cannot verify changes ahead on the integration branch.')
    if ahead and develop_tree != tree:
        ancestor_tree = comparison.get('merge_base_commit', {}).get('commit', {}).get('tree', {}).get('sha')
        require(develop_tree == ancestor_tree,
                f'{INTEGRATION} has unpromoted changes; promote them through a PR before releasing.')
    # Content-neutral back-merge commits are allowed.
    requested = tuple(map(int, version.split('.')))
    prefix = CONFIG.get('tag_prefix', '')
    for page in range(1, 11):
        releases = api(base + f'/releases?per_page=100&page={page}')
        require(isinstance(releases, list), 'Cannot verify published release versions.')
        for item in releases:
            tag = item.get('tag_name', '')
            if item.get('draft') or item.get('prerelease') or not tag.startswith(prefix) \
                    or not re.fullmatch(SEMVER, tag[len(prefix):]):
                continue
            published = tuple(map(int, tag[len(prefix):].split('.')))
            require(requested > published or (requested == published and item.get('target_commitish') == sha),
                    'Release version must exceed published versions; only the same source may resume.')
        if len(releases) < 100:
            return
    raise RuntimeError('Published release history exceeded its safety bound.')


def source(api=get, sha=None):
    sha = sha or os.environ['GITHUB_SHA']
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY, 'Unexpected repository.')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/' + PRODUCTION, f'Publication requires {PRODUCTION}.')
    base = '/repos/' + REPOSITORY
    current = api(base + '/commits/' + PRODUCTION)
    require(current['sha'] == sha, f'{PRODUCTION} changed; start a new release run.')
    tree = current['commit']['tree']['sha']
    release_request(api, sha, tree)
    runs = api(base + '/actions/workflows/ci.yml/runs?event=pull_request&status=success&per_page=50')
    for run in runs.get('workflow_runs', []):
        if (run.get('event') != 'pull_request' or run.get('conclusion') != 'success'
                or run.get('head_repository', {}).get('full_name') != REPOSITORY):
            continue
        tested = api(base + '/commits/' + run['head_sha'])
        if tested['commit']['tree']['sha'] == tree:
            jobs = api(base + '/actions/runs/' + str(run['id']) + '/jobs?per_page=100').get('jobs', [])
            checks = {job.get('name'): job.get('conclusion') for job in jobs}
            if any(checks.get(name) != 'success' for name in REQUIRED_JOBS):
                continue
            print('Exact source tree has successful prior PR validation.')
            return
    raise RuntimeError('No successful PR validation for this exact source tree.')


def approved(reviews, environment_id):
    relevant = [review for review in reviews if any(
        env.get('id') == environment_id and env.get('name') == 'production'
        for env in review.get('environments', []))]
    if any(review.get('state') == 'rejected' for review in relevant):
        return False
    return any(review.get('state') == 'approved'
               and review.get('user', {}).get('type') == 'User'
               and review.get('user', {}).get('id') == OWNER_ID for review in relevant)


def approval():
    require(OWNER_ID, 'production_reviewer.id is not configured.')
    source()
    base = '/repos/' + REPOSITORY
    environment = get(base + '/environments/production')
    reviewers = [reviewer for rule in environment.get('protection_rules', [])
                 if rule.get('type') == 'required_reviewers' for reviewer in rule.get('reviewers', [])]
    require(len(reviewers) == 1 and reviewers[0].get('type') == 'User'
            and reviewers[0].get('reviewer', {}).get('id') == OWNER_ID,
            'Production reviewer policy changed.')
    policy = environment.get('deployment_branch_policy') or {}
    branches = get(base + '/environments/production/deployment-branch-policies').get('branch_policies', [])
    require(policy.get('custom_branch_policies') is True
            and len(branches) == 1 and branches[0].get('name') == PRODUCTION
            and branches[0].get('type') == 'branch', f'Production must allow only {PRODUCTION}.')
    run_id = os.environ['GITHUB_RUN_ID']
    run = get(base + '/actions/runs/' + run_id)
    require(run.get('head_sha') == os.environ['GITHUB_SHA']
            and run.get('head_branch') == PRODUCTION
            and run.get('event') == 'workflow_dispatch'
            and run.get('path') == '.github/workflows/release.yml',
            'Approval does not belong to this release source.')
    reviews = get(base + '/actions/runs/' + run_id + '/approvals')
    require(isinstance(reviews, list) and approved(reviews, environment['id']),
            'No eligible human production approval receipt; bypass is not approval.')
    print('Human production approval receipt verified.')


if __name__ == '__main__':
    try:
        {'source': source, 'approval': approval}[sys.argv[1]]()
    except Exception as error:
        # Exceptions never contain token values; do not print HTTP response bodies.
        print(f'Release authorization failed: {type(error).__name__}: {error}', file=sys.stderr)
        raise SystemExit(1)
