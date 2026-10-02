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

and the card's own sprites, which the page draws the card with, from assets/dyn/ui/[uc]namecardv2/
(the level ring, the share, signature and support icons, the outfit hanger, the Rhodes Island and
Human Resource marks, the disc behind each nation's emblem) and the elite and potential badges
from assets/dyn/arts/elite_hub/ and potential_hub/, each at its own size under its own name:

  .../module_avatar_simple/level_bg.png       -> profile-ui/level_bg.webp
  elite_hub/elite_2.png                       -> profile-ui/elite_2.webp

Only the sprites in UI_SPRITES are published; one the dump no longer has fails the run.

And each operator's portrait in each outfit, which the card shows its support units in, from
assets/dyn/arts/charportraits/ (180x360):

  charportraits/[skins/|linkages/]char_1013_chen2_boc#6.png
                                              -> profile-portraits/char_1013_chen2_boc_6.webp

named by the outfit's skin id as portrait_name() writes it (the page writes it the same way,
lib/account/portraits.ts): "@" and "#" are "_", and Amiya's "1+" is "1p". The same portrait is
in skins/ and linkages/ at a higher quality than at the top, so those copies win.

The file names are the game's ids, so the page needs no table to find them. The dump is read
at one commit for the whole run, and each file's git blob is recorded in
sources/profile-art.json, so a file is fetched again only when the game changes it. There are
some three thousand medals and thirteen hundred portraits: a run publishes at most MAX_NEW new
files (default 1500), and starts no new one after MAX_SECONDS (default 720, well inside the
job's 25 minutes, which a run of all the portraits overran and was cancelled with nothing
published); the next run carries on where it stopped.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import time
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
MAX_SECONDS = float(os.environ.get('MAX_SECONDS', '720'))
SOURCES = ROOT / 'sources' / 'profile-art.json'
# The card's sprites the page uses, by the folder each is listed from (ui_jobs).
UI_SPRITES = {
    'namecardv2': {
        'prefabs/module_avatar_simple/level_bg.png', 'prefabs/module_avatar_simple/share_btn.png',
        'prefabs/module_sign/resume_icon.png', 'prefabs/assist_icon.png', 'prefabs/team_back.png',
        'prefabs/assist_char/left_up_back.png', 'prefabs/assist_char/elite_and_potential_bg.png',
        'prefabs/module_collect/icon_skin.png', 'prefabs/module_collect/decor_skin.png',
        'prefabs/module_collect/human_resource.png', 'prefabs/module_collect/rhodes_island_decor.png',
        'prefabs/module_collect/no_use_icon_circle.png', 'prefabs/module_collect/no_use_icon_x.png',
        'crossappshare/remake_name_card_v2_simple_controller/name_card_uid_bg.png',
    },
    'elite_hub': {'elite_0.png', 'elite_1.png', 'elite_2.png'},
    'potential_hub': {f'potential_{level}_small.png' for level in range(6)},
}
PORTRAITS = 'assets/dyn/arts/charportraits'
UI_FOLDERS = {'namecardv2': 'assets/dyn/ui/[uc]namecardv2', 'elite_hub': 'assets/dyn/arts/elite_hub', 'potential_hub': 'assets/dyn/arts/potential_hub'}


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


def ui_jobs(listing):
    """(target, source path, blob sha, 'ui') for each of UI_SPRITES, from its folder's recursive
    git tree: {folder: [{path, sha, type}]}. A sprite the dump moved or removed fails the run."""
    for folder, wanted in UI_SPRITES.items():
        found = {entry['path']: entry['sha'] for entry in listing.get(folder, []) if entry['type'] == 'blob'}
        missing = sorted(wanted - set(found))
        if missing:
            raise ValueError(f'{UI_FOLDERS[folder]}: no {", ".join(missing)} (the dump moved them; update UI_SPRITES)')
        for path in sorted(wanted):
            yield f'profile-ui/{Path(path).stem}.webp', f'{UI_FOLDERS[folder]}/{path}', found[path], 'ui'


def portrait_name(skin_id):
    """The published name of an outfit's portrait: the skin id ("char_1013_chen2@boc#6",
    "char_002_amiya#1+") or the dump's file stem ("char_1013_chen2_boc#6"), the same for both."""
    return skin_id.replace('@', '_').replace('#', '_').replace('+', 'p')


def portrait_jobs(listing):
    """(target, source path, blob sha, 'portrait') for each operator outfit portrait, from the
    folder's recursive git tree; a skins/ or linkages/ copy wins over the top-level one."""
    rank = {'skins': 0, 'linkages': 1, '': 2}
    best = {}
    for entry in listing:
        match = re.fullmatch(r'(?:(skins|linkages)/)?(char_[\w#+-]+)\.png', entry['path'])
        if entry['type'] != 'blob' or not match:
            continue
        name = portrait_name(match.group(2))
        if not re.fullmatch(r'[\w-]+', name):
            continue
        if name not in best or rank[match.group(1) or ''] < rank[best[name][0]]:
            best[name] = (match.group(1) or '', entry)
    for name, (_, entry) in sorted(best.items()):
        yield f'profile-portraits/{name}.webp', f'{PORTRAITS}/{entry["path"]}', entry['sha'], 'portrait'


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
    if kind == 'ui':
        image.save(out, 'WEBP', lossless=True, method=6)
    else:
        image.save(out, 'WEBP', quality=82 if kind in ('bg', 'portrait') else 90, method=6)
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
    portraits = next((entry for entry in api(f'repos/{REPO}/contents/{PORTRAITS.rsplit("/", 1)[0]}?ref={commit}') if entry['name'] == 'charportraits'), None)
    if not portraits:
        raise ValueError(f'{PORTRAITS} is not in {REPO}@{commit[:12]}: the dump moved it')
    portrait_tree = api(f'repos/{REPO}/git/trees/{portraits["sha"]}?recursive=1')
    if portrait_tree.get('truncated'):
        raise ValueError('charportraits: the tree listing was truncated')
    ui_listing = {}
    for folder, path in UI_FOLDERS.items():
        parent, name = path.rsplit('/', 1)
        entry = next((entry for entry in api(f'repos/{REPO}/contents/{urllib.parse.quote(parent)}?ref={commit}') if entry['name'] == name), None)
        if not entry:
            raise ValueError(f'{path} is not in {REPO}@{commit[:12]}: the dump moved it')
        tree = api(f'repos/{REPO}/git/trees/{entry["sha"]}?recursive=1')
        if tree.get('truncated'):
            raise ValueError(f'{folder}: the tree listing was truncated')
        ui_listing[folder] = tree['tree']

    sources = json.loads(SOURCES.read_text()) if SOURCES.exists() else {}
    manifest_path = ROOT / 'asset-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    wanted = [job for job in [*ui_jobs(ui_listing), *jobs(listing), *portrait_jobs(portrait_tree['tree'])] if not (job[0] in manifest['files'] and sources.get(job[0]) == job[2])]
    changed = []
    deadline = time.monotonic() + MAX_SECONDS
    for target, path, blob, kind in wanted[:MAX_NEW]:
        if time.monotonic() > deadline:
            break
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
    left = len(wanted) - len(changed)
    print(f'Profile art at {REPO}@{commit[:12]}: {len(changed)} published' + (f', {left} left for the next run.' if left else ', all current.'))


if __name__ == '__main__':
    main()
