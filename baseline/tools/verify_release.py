"""Verify exact public-file inventory and hashes without numerical dependencies."""
from pathlib import Path, PurePosixPath
import hashlib
import json

BUNDLE = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(root=BUNDLE):
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    listed = set()
    for item in manifest['files']:
        relative = PurePosixPath(item['path'])
        if relative.is_absolute() or '..' in relative.parts or '\\' in item['path']:
            raise ValueError('Unsafe manifest path')
        if item['path'] in listed:
            raise ValueError('Duplicate manifest entry')
        listed.add(item['path'])
        path = root.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing or linked file: ' + item['path'])
        if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError('File integrity mismatch: ' + item['path'])
    found = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('Linked path not allowed')
        if path.is_file():
            relative = path.relative_to(root)
            if '__pycache__' in relative.parts or '.pytest_cache' in relative.parts:
                continue
            found.add(relative.as_posix())
    if found != listed | {'MANIFEST.json', 'SHA256SUMS'}:
        raise ValueError('Unexpected or missing public files: ' + str(found ^ (listed | {'MANIFEST.json', 'SHA256SUMS'})))
    expected = {item['path']: item['sha256'] for item in manifest['files']}
    expected['MANIFEST.json'] = digest(root / 'MANIFEST.json')
    sums = {}
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        value, name = line.split('  ', 1)
        if name in sums:
            raise ValueError('Duplicate checksum entry')
        sums[name] = value
    if expected != sums:
        raise ValueError('Checksum index mismatch')
    return {'status': 'PASS', 'files_verified': len(listed), 'manifest_sha256': expected['MANIFEST.json']}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
