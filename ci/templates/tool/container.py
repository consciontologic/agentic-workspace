"""Build once, smoke-test and publish the exact approved container image to GHCR."""
import argparse
import gzip
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release import (CONFIG, PROJECT, REPOSITORY, ROOT, fingerprint, release_version, source_sha,  # noqa: E402
                     verify_bundle, write_identity)

SETTINGS = CONFIG['container']
OUTPUT = ROOT / 'build/release'


def run(*args, capture=False, check=True):
    return subprocess.run(list(args), check=check, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.DEVNULL if capture else None)


def image_tag():
    return f'{SETTINGS["image"]}:{release_version()}'


def inspect(tag):
    return json.loads(run('docker', 'image', 'inspect', tag, capture=True).stdout)[0]


def build():
    identity = verify_bundle(OUTPUT)
    tag = image_tag()
    run('docker', 'build', '--pull', '--platform=linux/amd64',
        '--label=org.opencontainers.image.source=https://github.com/' + REPOSITORY,
        '--label=org.opencontainers.image.revision=' + source_sha(),
        '--label=org.opencontainers.image.version=' + identity['version'],
        '--file=' + str(ROOT / SETTINGS['dockerfile']), '--tag=' + tag, str(ROOT / SETTINGS['context']))
    info = inspect(tag)
    if info['Os'] != 'linux' or info['Architecture'] != 'amd64':
        raise ValueError('Image platform differs from linux/amd64.')
    if info['Config']['User'] in ('', '0', 'root', '0:0'):
        raise ValueError('Image must run as a non-root user.')
    archive = OUTPUT / f'{PROJECT}-{identity["version"]}-linux-amd64.tar.gz'
    with archive.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as target:
        process = subprocess.Popen(['docker', 'save', tag], stdout=subprocess.PIPE)
        try:
            shutil.copyfileobj(process.stdout, target)
        finally:
            process.stdout.close()
        if process.wait() != 0:
            raise RuntimeError('Docker could not save the release image.')
    identity['container_id'] = info['Id']
    identity['artifacts'][archive.name] = fingerprint(archive)
    write_identity(OUTPUT, identity)
    print('Saved immutable linux/amd64 image ' + info['Id'])


def smoke():
    tag = image_tag()
    port = str(SETTINGS.get('smoke_port', 8080))
    name = f'{PROJECT}-smoke'
    run('docker', 'rm', '-f', name, check=False, capture=True)
    run('docker', 'run', '-d', '--name', name, '--read-only', '--cap-drop=ALL', '--tmpfs', '/tmp',
        '--tmpfs', '/var/cache/nginx', '--tmpfs', '/run', '--security-opt=no-new-privileges',
        '-p', f'127.0.0.1:{port}:{port}', tag, capture=True)
    try:
        for _ in range(30):
            try:
                connection = http.client.HTTPConnection('127.0.0.1', int(port), timeout=2)
                connection.request('GET', SETTINGS.get('smoke_path', '/'))
                if connection.getresponse().status == 200:
                    print('Read-only container smoke passed.')
                    return
            except OSError:
                pass
            time.sleep(1)
        raise RuntimeError('Container did not answer HTTP 200 in time.')
    finally:
        run('docker', 'rm', '-f', name, check=False, capture=True)


def preflight():
    tag = image_tag()
    exists = run('docker', 'manifest', 'inspect', tag, check=False, capture=True).returncode == 0
    if exists:
        raise ValueError(f'{tag} already exists; package versions are immutable.')
    print('Package version is free.')


def publish():
    identity = verify_bundle(OUTPUT, require_container=True)
    tag = image_tag()
    archive = OUTPUT / f'{PROJECT}-{identity["version"]}-linux-amd64.tar.gz'
    run('docker', 'load', '--input', str(archive))
    if inspect(tag)['Id'] != identity['container_id']:
        raise ValueError('Loaded image differs from the approved image.')
    run('docker', 'push', tag)
    print('Published ' + tag)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['build', 'smoke', 'preflight', 'publish'])
    {'build': build, 'smoke': smoke, 'preflight': preflight, 'publish': publish}[parser.parse_args().command]()
