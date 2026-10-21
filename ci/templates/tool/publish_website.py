"""GitOps publication of a verified build into a separate GitHub Pages repository.

Only paths listed in the managed manifest are ever removed; other content is kept.
Usage: PAGES_DEPLOY_TOKEN=... python3 tool/publish_website.py <verified-build-dir>
"""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release import CONFIG, REPOSITORY, release_version, site_files, source_sha  # noqa: E402

SETTINGS = CONFIG['pages_repo']
MANIFEST = '.managed-files.json'


def git(*args, cwd, env):
    return subprocess.run(['git', *args], cwd=cwd, env=env, check=True, text=True,
                          stdout=subprocess.PIPE).stdout.strip()


def publish(build, token, workdir=None):
    files = site_files(build)
    version, sha = release_version(), source_sha()
    header = 'AUTHORIZATION: basic ' + base64.b64encode(f'x-access-token:{token}'.encode()).decode()
    # The token travels via environment config, never argv or the remote URL.
    env = {**os.environ, 'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'http.https://github.com/.extraheader',
           'GIT_CONFIG_VALUE_0': header, 'GIT_TERMINAL_PROMPT': '0'}
    with tempfile.TemporaryDirectory() as scratch:
        clone = Path(workdir or scratch) / 'site'
        git('clone', '--depth=1', '--branch', SETTINGS['branch'],
            f'https://github.com/{SETTINGS["repository"]}.git', str(clone), cwd=scratch, env=env)
        destination = clone / SETTINGS.get('subdir', '')
        destination.mkdir(parents=True, exist_ok=True)
        manifest = destination / MANIFEST
        previous = json.loads(manifest.read_text()) if manifest.exists() else {}
        for name in set(previous) - set(files):
            stale = destination / name
            if stale.is_file():
                stale.unlink()
        for name in files:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(build) / name, target)
        manifest.write_text(json.dumps(files, indent=2, sort_keys=True) + '\n')
        git('add', '-A', cwd=clone, env=env)
        if not git('status', '--porcelain', cwd=clone, env=env):
            print('Website already matches the release.')
            return
        git('-c', 'user.name=github-actions[bot]', '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
            'commit', '-m', f'release: {version}\n\nSource: {REPOSITORY}@{sha}', cwd=clone, env=env)
        git('push', 'origin', 'HEAD:' + SETTINGS['branch'], cwd=clone, env=env)
        print('Published website commit ' + git('rev-parse', 'HEAD', cwd=clone, env=env))


if __name__ == '__main__':
    publish(sys.argv[1], os.environ['PAGES_DEPLOY_TOKEN'])
