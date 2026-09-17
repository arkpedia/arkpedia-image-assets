#!/usr/bin/env python3
"""Enter hand-placed images into asset-manifest.json.

Every image in this repository has to be listed in asset-manifest.json with its
byte count and SHA-256: validate_images.py fails a push where a tracked image is
unlisted. Until now only sync_images.py wrote those rows, and it only ever touches
files it pulled from the upstream mirror through asset-source-map.json. So an image
added by hand -- art the mirror does not carry, a correction, a capture -- could not
be committed at all without someone typing a hash into the manifest.

This does that arithmetic instead. Drop the file into its delivery folder, run this,
and commit the result:

    cp 'Bellone - Outstanding Debt.webp' base-skill-icons/
    python scripts/add_local_assets.py
    git add base-skill-icons asset-manifest.json && git commit

It only ever ADDS rows. An image already in the manifest is left alone even if its
bytes differ on disk, because that is either an upstream file the sync owns or a
replacement that should be reviewed on its own -- not something a convenience script
should overwrite. --replace opts into that, one named path at a time.
"""
import argparse
import hashlib
import io
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MEDIA = {'.png', '.webp', '.jpg', '.jpeg', '.avif', '.gif', '.ico', '.svg'}
MAX_BYTES = 100 * 1024 * 1024


def tracked_and_untracked():
    """Every media path git would commit: already tracked, or new and not ignored."""
    out = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    for path in out.decode().split('\0'):
        if path and Path(path).suffix.lower() in MEDIA and not path.startswith('scripts/'):
            yield path


def measure(path):
    """The same checks validate_images.py applies, so a row this writes cannot fail CI."""
    data = (ROOT / path).read_bytes()
    if not 0 < len(data) < MAX_BYTES:
        raise ValueError(f'Empty or oversized image: {path}')
    if Path(path).suffix.lower() == '.svg':
        ET.fromstring(data)
    else:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.width <= 0 or image.height <= 0:
                raise ValueError(f'Invalid image dimensions: {path}')
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--replace', action='append', default=[], metavar='PATH',
                        help='Re-measure this already-listed path. Repeatable. Use when you deliberately '
                             'replaced an existing image; review the diff before committing.')
    parser.add_argument('--dry-run', action='store_true', help='Report what would change and write nothing.')
    args = parser.parse_args()

    manifest_path = ROOT / 'asset-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    files = manifest['files']

    for path in args.replace:
        if path not in files:
            raise SystemExit(f'--replace {path} is not in the manifest; drop the flag and it will be added.')
        if not (ROOT / path).exists():
            raise SystemExit(f'--replace {path} does not exist on disk.')

    # Rows the skin repository nests under an entry (original/variants) are listed
    # there rather than at the top level; mirror validate_images.py so they are not
    # mistaken for unlisted files.
    listed = set(files)
    for row in files.values():
        if row.get('original'):
            listed.add(row['original']['path'])
        for widths in row.get('variants', {}).values():
            for variant in widths.values():
                listed.add(variant['path'])

    added, replaced = {}, {}
    for path in sorted(tracked_and_untracked()):
        if path in listed:
            if path in args.replace:
                row = measure(path)
                if row != files.get(path):
                    replaced[path] = row
            continue
        added[path] = measure(path)

    if not added and not replaced:
        print('Nothing to add: every image on disk is already listed with its current bytes.')
        return

    for path, row in added.items():
        print(f'  + {path}  ({row["bytes"]} bytes)')
    for path, row in replaced.items():
        print(f'  ~ {path}  ({files[path]["bytes"]} -> {row["bytes"]} bytes)')

    if args.dry_run:
        print(f'\nDry run: {len(added)} to add, {len(replaced)} to replace. Nothing written.')
        return

    files.update(added)
    files.update(replaced)
    manifest['files'] = dict(sorted(files.items()))
    # Byte-for-byte the format sync_images.py writes, so the two never fight over the file.
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f'\nasset-manifest.json: {len(added)} added, {len(replaced)} replaced. '
          f'Commit it together with the images, then run `npm run assets:update` in the app.')


if __name__ == '__main__':
    main()
