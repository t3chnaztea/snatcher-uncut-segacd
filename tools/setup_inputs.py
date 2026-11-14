#!/usr/bin/env python3
"""Validate user-supplied inputs and create only their ignored manifest.

No game, BIOS, reference tool or credential is downloaded or copied.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def setup(root=ROOT):
    root = Path(root).resolve()
    specification = json.loads((root/'config/input-manifest.json').read_text())
    rows = specification['inputs']
    if specification.get('version') != 1 or len(rows) != 32:
        raise ValueError('Expected the version 1 specification with 32 inputs')
    paths = set()
    for row in rows:
        relative = PurePosixPath(row['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.as_posix() in paths:
            raise ValueError('Unsafe or duplicate input path')
        paths.add(relative.as_posix())
        path = root/'private'/relative
        if not path.is_file():
            raise ValueError('Stage the user-supplied input: private/'+row['path'])
        if path.stat().st_size != row['bytes']:
            raise ValueError('Input size differs: '+row['path'])
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha1').hexdigest()
        if actual != row['sha1']:
            raise ValueError('Input SHA1 differs: '+row['path'])
    reference = specification['reference']
    checkout = root/reference['path']
    revision = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'],
                              check=True, capture_output=True, text=True).stdout.strip()
    if revision != reference['revision'] or not (checkout/'pce/tools/pcescript.py').is_file():
        raise ValueError('The pinned PCE reference checkout is required')
    clean = subprocess.run(['git', '-C', str(checkout), 'diff', '--quiet', 'HEAD',
                            '--', 'pce/tools', 'pce/translation'], capture_output=True)
    if clean.returncode != 0:
        raise ValueError('The pinned reference tools or translation files are modified')
    manifest = root/'private/MANIFEST.md'
    expected = {(r['path'], r['bytes'], r['sha1']) for r in rows}
    if manifest.exists():
        existing = [(p, int(n.replace(',', '')), h) for p, n, h in re.findall(
            r'^\| `([^`]+)` \| ([\d,]+) \| `([0-9a-f]{40})`', manifest.read_text(), re.M)]
        if len(existing) != 32 or set(existing) != expected:
            raise ValueError('Existing private manifest differs; it was not overwritten')
        created = False
    else:
        text = '# User-supplied inputs\n\nGenerated after size and SHA1 verification.\n\n'
        text += '| File | Bytes | SHA1 |\n|---|---:|---|\n'
        text += ''.join(f"| `{r['path']}` | {r['bytes']:,} | `{r['sha1']}` |\n" for r in rows)
        manifest.write_text(text)
        created = True
    return dict(status='verified', inputs=32, manifest_created=created,
                reference_revision=revision)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    print(json.dumps(setup(parser.parse_args().root)))
