"""Check staged blobs without printing credentials or reading private signing keys."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main():
    secrets = []
    env_path = ROOT / '.env'
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('\"\'')
            if sep and re.search(r'PASSWORD|SECRET|TOKEN|PEPPER|PRIVATE|SERVICE_ROLE', key, re.I) and len(value) >= 8:
                secrets.append(value.encode())
    names = [name.decode('utf-8') for name in git('diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z').split(b'\0') if name]
    issues = []
    for name in names:
        path = Path(name)
        if (path.name.startswith('.env') and path.name != '.env.example') or path.suffix.lower() in {'.pfx', '.p12', '.key', '.pem', '.clixml', '.sqlite', '.db'} or '.local' in path.parts:
            issues.append((name, 'private/local file'))
            continue
        data = git('show', ':' + name)
        if any(secret in data for secret in secrets):
            issues.append((name, 'matches local credential'))
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----', data):
            issues.append((name, 'private key material'))
    if issues:
        for name, reason in issues:
            print(f'BLOCKED {name}: {reason}')
        return 1
    print(f'PASS: {len(names)} staged files; no local credentials or private-key files detected.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
