#!/usr/bin/env python3
"""Publish the art of the game's player profile card, for the website's account page.

An imported account (arkpedia/arkpedia, lib/account) names its avatar, its business card
style and the medals on its medal board by the game's ids. Their art is in the Global
client's dump, ArknightsAssets/ArknightsAssets2 (branch en), under assets/dyn/arts/ui/:

  playeravatar/<id>.png                       -> profile-avatars/<id>.webp        (150px)
  namecardskin/[uc]<id>/skin_style/bg.png     -> profile-namecards/<id>-bg.webp    (1280 wide)
  namecardskin/[uc]<id>/skin_style/name_card_long.png
                                              -> profile-namecards/<id>-strip.webp
  medalicon/<group>/<medal id>.png            -> profile-medals/<medal id>.webp   (96px tall)

The file names are the game's ids, so the page needs no table to find them. The dump is read
at one commit for the whole run, and each file's git blob is recorded in
sources/profile-art.json, so a file is fetched again only when the game changes it. There are
some three thousand medals: a run publishes at most MAX_NEW new files (default 1500) and the
next run carries on, so no run outlasts the job's time limit.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REPO = 'ArknightsAssets/ArknightsAssets2'
BRANCH = 'en'
UI = 'assets/dyn/arts/ui'
UA = 'Arkpedia-assets/1.0 (+https://arkpedia.net)'
SSL = __import__('ssl').create_default_context(cafile=certifi.where())
MAX_NEW = int(os.environ.get('MAX_NEW', '1500'))
SOURCES = ROOT / 'sources' / 'profile-art.json'


def api(path):
    headers = {'User-Agent': UA, 'Accept': 'application/vnd.github+json'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(f'https://api.github.com/{path}', headers=headers), context=SSL, timeout=120) as response:
        return json.load(response)


def fetch(commit, path):
    url = f'https://raw.githubusercontent.com/{REPO}/{commit}/{urllib.parse.quote(path, safe="/")}'
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), context=SSL, timeout=120) as response:
        return response.read()


def jobs(listing):
    """(target, source path, blob sha, kind) for every file the page can use, from the three
    folders' recursive git trees: {folder: [{path, sha, type}]}."""
    for entry in listing.get('playeravatar', []):
        name = entry['path']
        if entry['type'] == 'blob' and re.fullmatch(r'[\w-]+\.png', name):
            yield f'profile-avatars/{name[:-4]}.webp', f'{UI}/playeravatar/{name}', entry['sha'], 'avatar'
    for entry in listing.get('namecardskin', []):
        match = re.fullmatch(r'\[uc\](nc_[\w-]+)/skin_style/(bg|name_card_long)\.png', entry['path'])
        if entry['type'] == 'blob' and match:
            card, part = match.groups()
            yield f'profile-namecards/{card}-{"bg" if part == "bg" else "strip"}.webp', f'{UI}/namecardskin/{entry["path"]}', entry['sha'], part
    for entry in listing.get('medalicon', []):
        match = re.fullmatch(r'[\w-]+/(medal_[\w-]+)\.png', entry['path'])
        if entry['type'] == 'blob' and match:
            yield f'profile-medals/{match.group(1)}.webp', f'{UI}/medalicon/{entry["path"]}', entry['sha'], 'medal'


def convert(data, kind):
    """The source PNG, sized for the page, as WebP bytes and its (width, height)."""
    with Image.open(io.BytesIO(data)) as source:
        source.load()
        if not 0 < source.width <= 8192 or not 0 < source.height <= 8192:
            raise ValueError(f'Invalid image dimensions {source.size}')
        image = source.convert('RGB' if kind == 'bg' else 'RGBA')
    if kind == 'bg' and image.width > 1280:
        image = image.resize((1280, round(image.height * 1280 / image.width)), Image.Resampling.LANCZOS)
    if kind == 'medal' and image.height > 96:
        image = image.resize((round(image.width * 96 / image.height), 96), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, 'WEBP', quality=82 if kind == 'bg' else 90, method=6)
    return out.getvalue(), image.size


def main():
    commit = api(f'repos/{REPO}/commits/{BRANCH}')['sha']
    folders = {entry['name']: entry['sha'] for entry in api(f'repos/{REPO}/contents/{UI}?ref={commit}') if entry['type'] == 'dir'}
    listing = {}
    for folder in ('playeravatar', 'namecardskin', 'medalicon'):
        if folder not in folders:
            raise ValueError(f'{UI}/{folder} is not in {REPO}@{commit[:12]}: the dump moved it')
        tree = api(f'repos/{REPO}/git/trees/{folders[folder]}?recursive=1')
        if tree.get('truncated'):
            raise ValueError(f'{folder}: the tree listing was truncated')
        listing[folder] = tree['tree']

    sources = json.loads(SOURCES.read_text()) if SOURCES.exists() else {}
    manifest_path = ROOT / 'asset-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    wanted = [job for job in jobs(listing) if not (job[0] in manifest['files'] and sources.get(job[0]) == job[2])]
    changed = []
    for target, path, blob, kind in wanted[:MAX_NEW]:
        content, (width, height) = convert(fetch(commit, path), kind)
        (ROOT / target).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / target).write_bytes(content)
        manifest['files'][target] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(), 'width': width, 'height': height}
        sources[target] = blob
        changed.append(target)

    if changed:
        manifest['files'] = dict(sorted(manifest['files'].items()))
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n')
        SOURCES.parent.mkdir(parents=True, exist_ok=True)
        SOURCES.write_text(json.dumps(dict(sorted(sources.items())), indent=2) + '\n')
        subprocess.run(['git', 'add', '--sparse', '--', 'asset-manifest.json', str(SOURCES.relative_to(ROOT)), *changed], cwd=ROOT, check=True)
    left = max(0, len(wanted) - MAX_NEW)
    print(f'Profile art at {REPO}@{commit[:12]}: {len(changed)} published' + (f', {left} left for the next run.' if left else ', all current.'))


if __name__ == '__main__':
    main()
