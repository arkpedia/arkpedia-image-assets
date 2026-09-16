#!/usr/bin/env python3
"""Refresh reviewed image mappings directly from a public game-resource mirror.

Never delete assets or guess a renamed source. Unmapped/manual artwork stays intact.
The source map records exact upstream paths and Git blob IDs for incremental updates.
"""
import hashlib
import io
import json
import os
import subprocess
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REPO = 'yuanyan3060/ArknightsGameResource'

def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path]))

def fetch(path, sha):
    url = f'https://raw.githubusercontent.com/{REPO}/{sha}/{urllib.parse.quote(path, safe="/")}'
    return subprocess.check_output(['curl', '-fsSL', '--retry', '3', '--max-time', '90', url])

def sync_one(job):
    asset, entry, source_blob, revision = job
    data = fetch(entry['sourcePath'], revision)
    actual_blob = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
    if actual_blob != source_blob:
        raise ValueError(f'Upstream blob mismatch: {asset}')
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        if not 0 < image.width <= 16384 or not 0 < image.height <= 16384:
            raise ValueError(f'Invalid dimensions: {asset}')
        image = image.convert('RGBA')
        max_width = entry.get('maxWidth', 180)
        if image.width > max_width:
            image = image.resize((max_width, max(1, round(image.height * max_width / image.width))), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format='WEBP', quality=90, method=4)
        encoded = output.getvalue()
        target = ROOT / asset
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        temporary.write_bytes(encoded)
        os.replace(temporary, target)
        row = {'bytes': len(encoded), 'sha256': hashlib.sha256(encoded).hexdigest(), 'width': image.width, 'height': image.height}
    return asset, row, source_blob

def main():
    mapping_path = ROOT / 'asset-source-map.json'
    mapping = json.loads(mapping_path.read_text())
    manifest_path = ROOT / 'asset-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    revision = api(f'repos/{REPO}/commits/main')['sha']
    tree = api(f'repos/{REPO}/git/trees/{revision}?recursive=1')
    if tree.get('truncated'):
        raise ValueError('Incomplete upstream tree; refusing refresh')
    blobs = {row['path']: row['sha'] for row in tree['tree'] if row['type'] == 'blob'}
    jobs = []
    for asset, entry in mapping['files'].items():
        if Path(asset).is_absolute() or '..' in Path(asset).parts:
            raise ValueError(f'Unsafe destination: {asset}')
        blob = blobs.get(entry['sourcePath'])
        if not blob:
            raise ValueError(f'Upstream removed {entry["sourcePath"]}; review mapping, existing assets preserved')
        if blob != entry.get('sourceBlob'):
            jobs.append((asset, entry, blob, revision))
    if len(jobs) > max(100, len(mapping['files']) * .25) and mapping.get('lastSyncedCommit'):
        raise ValueError(f'{len(jobs)} images changed together; review upstream/map before accepting a bulk replacement')
    changed = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for asset, row, blob in pool.map(sync_one, jobs):
            manifest['files'][asset] = row
            mapping['files'][asset]['sourceBlob'] = blob
            changed.append(asset)
    mapping['lastSyncedCommit'] = revision
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n')
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + '\n')
    for offset in range(0, len(changed), 100):
        subprocess.run(['git', 'add', '--sparse', '--', *changed[offset:offset+100]], cwd=ROOT, check=True)
    subprocess.run(['git', 'add', '--sparse', 'asset-manifest.json', 'asset-source-map.json'], cwd=ROOT, check=True)
    print(f'Checked {len(mapping["files"])} reviewed mappings; refreshed {len(changed)} images from {revision}.')

if __name__ == '__main__':
    main()
