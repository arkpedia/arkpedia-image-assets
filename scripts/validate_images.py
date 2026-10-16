#!/usr/bin/env python3
"""Validate manifest inventory plus decoded image bytes (full or staged changes)."""
import argparse
import hashlib
import io
import json
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MEDIA = {'.png', '.webp', '.jpg', '.jpeg', '.avif', '.gif', '.ico', '.svg'}

# Existing aliases have different bytes. Preserve both until their consumers and
# provenance have a reviewed migration; new collisions must not join this debt.
KNOWN_CASE_COLLISIONS = {
    frozenset({'one-star-icons/Gallus² - Base.webp', 'one-star-icons/GALLUS² - Base.webp'}):
        'Existing case-only aliases; preserve both published originals pending a reviewed migration.',
}

def manifest_records(manifest):
    records = {}
    for path, row in manifest['files'].items():
        records[path] = row
        if row.get('original'):
            records[row['original']['path']] = row['original']
        for widths in row.get('variants', {}).values():
            for variant in widths.values():
                records[variant['path']] = variant
    return records

def validate_case_inventory(paths, allowed=KNOWN_CASE_COLLISIONS):
    """Full inventory policy, even when only staged image bytes are decoded."""
    grouped = {}
    for path in paths:
        key = unicodedata.normalize('NFC', path).casefold()
        grouped.setdefault(key, set()).add(path)
    collisions = {frozenset(group) for group in grouped.values() if len(group) > 1}
    unexpected = collisions - allowed.keys()
    if unexpected:
        raise ValueError(f'New case-insensitive media collisions: {sorted(sorted(group) for group in unexpected)}')
    stale = allowed.keys() - collisions
    if stale:
        raise ValueError(f'Remove resolved case-collision exceptions: {sorted(sorted(group) for group in stale)}')
    if any(not str(reason).strip() for reason in allowed.values()):
        raise ValueError('Every case-collision exception needs a reason')
    return len(collisions)

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def retired_paths():
    """retired-assets.json: published paths removed on purpose, each with its reason. arkpedia/arkpedia's
    pin step refuses any other removal (scripts/lib/published-asset-index.mjs), so a removal is
    listed here in the same PR that deletes the file."""
    path = ROOT / 'retired-assets.json'
    if not path.exists():
        return {}
    document = json.loads(path.read_text())
    if document.get('schemaVersion') != 1 or not isinstance(document.get('paths'), dict):
        raise ValueError('retired-assets.json must be {"schemaVersion": 1, "paths": {"<path>": {"reason": ...}}}')
    for item, entry in document['paths'].items():
        parts = Path(item).parts
        if Path(item).is_absolute() or item.startswith('.') or '..' in parts or '.' in parts:
            raise ValueError(f'retired-assets.json: unsafe path: {item}')
        if not isinstance(entry, dict) or not str(entry.get('reason', '')).strip():
            raise ValueError(f'retired-assets.json: {item} gives no reason')
    return document['paths']

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--staged', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'asset-manifest.json').read_text())
    records = manifest_records(manifest)
    legacy_collisions = validate_case_inventory(records)
    tracked = {p for p in git('ls-files', '-z').decode().split('\0') if p}
    media = {p for p in tracked if Path(p).suffix.lower() in MEDIA and not p.startswith('scripts/')}
    missing = set(records) - tracked
    unlisted = media - records.keys()
    if missing or unlisted:
        raise ValueError(f'Inventory mismatch: missing={sorted(missing)[:12]}, unlisted={sorted(unlisted)[:12]}')
    retired = retired_paths()
    still = sorted(p for p in retired if p in records or p in tracked)
    if still:
        raise ValueError(f'Retired but still published: {still[:12]}')
    if args.staged:
        deleted = git('diff', '--cached', '--name-only', '--diff-filter=D', '-z').decode().split('\0')
        if any(Path(p).suffix.lower() in MEDIA for p in deleted if p):
            raise ValueError('Automated media deletion is forbidden; review it in a separate PR')
        paths = set(git('diff', '--cached', '--name-only', '-z').decode().split('\0')) & records.keys()
    else:
        paths = records.keys()
    for path in sorted(paths):
        if Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError(f'Unsafe path: {path}')
        local = ROOT / path
        data = local.read_bytes() if local.exists() else git('show', f':{path}')
        row = records[path]
        if not 0 < len(data) < 100 * 1024 * 1024:
            raise ValueError(f'Empty or oversized image: {path}')
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError(f'Hash/size mismatch: {path}')
        if Path(path).suffix.lower() == '.svg':
            ET.fromstring(data)
            continue
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.width <= 0 or image.height <= 0:
                raise ValueError(f'Invalid image dimensions: {path}')
            if row.get('width') and (image.width, image.height) != (row['width'], row['height']):
                raise ValueError(f'Dimensions differ from manifest: {path}')
    print(f'Validated complete inventory ({len(records)} paths), decoded and hashed {len(paths)} images.')
    if legacy_collisions:
        print(f'Preserved {legacy_collisions} reviewed legacy case-collision group; no new collisions allowed.')

if __name__ == '__main__':
    main()
