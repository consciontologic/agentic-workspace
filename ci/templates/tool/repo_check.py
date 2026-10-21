"""Fail when tracked source contains credentials or unpinned workflow actions."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SECRETS = {
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}'),
    'AWS access key': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
}
USES = re.compile(r'^\s*-?\s*uses:\s*(\S+)', re.M)
PINNED = re.compile(r'[^@\s]+@[0-9a-f]{40}$')


def problems(root=ROOT):
    found = []
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    for name in filter(None, files):
        path = root / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        if name == 'tool/repo_check.py' or name.startswith('test/'):
            continue
        for label, pattern in SECRETS.items():
            if pattern.search(text):
                found.append(f'{name}: possible {label}')
        if name.startswith('.github/workflows/'):
            for ref in USES.findall(text):
                if not ref.startswith('./') and not PINNED.fullmatch(ref):
                    found.append(f'{name}: action {ref} is not pinned to a full commit SHA')
    return found


if __name__ == '__main__':
    issues = problems()
    for issue in issues:
        print('Repository check failed: ' + issue, file=sys.stderr)
    raise SystemExit(1 if issues else 0)
