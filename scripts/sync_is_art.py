#!/usr/bin/env python3
"""Publish IS sprites and Contingency Contract interface art by native ID, preferring Global over CN on every daily sync."""
import argparse
import concurrent.futures
import hashlib
import io
import json
import re
import subprocess
import urllib.parse
from pathlib import Path
from PIL import Image
from sync_profile_art import api, fetch, REPO

ROOT = Path(__file__).resolve().parents[1]
ART = 'assets/dyn/arts/ui/rogueliketopic'
UI = 'assets/dyn/ui/rogueliketopic/topics'
DEST = 'content-art/integrated-strategies'
ART_FOLDERS = {'itempic', 'choicepic', 'outerbufficon', 'recruitgrppic', 'rarity'}
# A theme's key art and title logo: read whole, they are not named by any table.
KEY_VISUALS = 'entrykeyvisuals'
# Ending pictures are story CGs, named by each ending's bgId.
AVG = 'assets/dyn/avg/images'
# Contingency Contract Battleplan: contract glyphs, region logos, area pictures, rank marks, season banners.
CC = 'assets/dyn/arts/ui/[uc]crisisv2'
CC_FOLDERS = {'runeicon', 'stagelogo', 'mapareabg', 'rankicon', 'shopseasonback'}
CC_DEST = 'content-art/contingency-contract'
SOURCES = {DEST: 'sources/is-game-art.json', CC_DEST: 'sources/cc-game-art.json'}
MINIMUM = {DEST: 1000, CC_DEST: 400}


def icon_ids(value):
    found = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {'iconId', 'displayIconId', 'bossIconId'} and isinstance(child, str):
                found.add(child.lower())
            # A coin's picture is filed under its group, shared by every gilded variant.
            if key == 'groupId' and isinstance(child, str) and '_copper_' in child:
                found.add(child.lower())
            found.update(icon_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(icon_ids(child))
    return found


def cg_ids(value):
    """The story picture each ending names."""
    found = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'endings' and isinstance(child, dict):
                found.update(row['bgId'].lower() for row in child.values() if isinstance(row, dict) and isinstance(row.get('bgId'), str))
            found.update(cg_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(cg_ids(child))
    return found


def size_limit(target):
    """Icons stay icon-sized; pictures keep enough to fill a page hero."""
    if f'/{KEY_VISUALS}/' in target:
        return 1600
    if target.startswith(f'{DEST}/cg/'):
        return 1280
    if target.startswith(CC_DEST) and '/runeicon/' not in target:
        return 512
    return 192


def candidates(snapshots, declared, pictures=frozenset()):
    """Same exact asset path is Global first; CN-only sprites remain available."""
    selected = {}
    for region in ('cn', 'en'):
        snapshot = snapshots[region]
        for entry in snapshot['tree']:
            source = entry['path']
            if entry['type'] != 'blob' or not source.endswith('.png'):
                continue
            if source.startswith(ART + '/'):
                relative = source[len(ART) + 1:]
                folder = relative.split('/')[0]
                if folder not in ART_FOLDERS:
                    continue
                if folder == 'itempic' and Path(source).stem.lower() not in declared:
                    continue
            elif source.startswith(UI + '/'):
                if Path(source).stem.lower() not in declared and f'/{KEY_VISUALS}/' not in source:
                    continue
                relative = 'topics/' + source[len(UI) + 1:]
            elif source.startswith(AVG + '/'):
                if Path(source).stem.lower() not in pictures:
                    continue
                relative = 'cg/' + source[len(AVG) + 1:]
            elif source.startswith(CC + '/'):
                relative = source[len(CC) + 1:]
                if relative.split('/')[0] not in CC_FOLDERS:
                    continue
                selected[f'{CC_DEST}/{relative[:-4]}.webp'] = {'sourceRegion': region, 'sourceCommit': snapshot['commit'], 'sourcePath': source, 'sourceBlob': entry['sha']}
                continue
            else:
                continue
            target = f'{DEST}/{relative[:-4]}.webp'
            selected[target] = {'sourceRegion': region, 'sourceCommit': snapshot['commit'], 'sourcePath': source, 'sourceBlob': entry['sha']}
    return selected


def convert(content, limit=192):
    image = Image.open(io.BytesIO(content)).convert('RGBA')
    image.thumbnail((limit, limit), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, 'WEBP', quality=90, method=4)
    return output.getvalue(), image.size


def snapshots_from_upstream():
    from urllib.request import Request, urlopen
    from sync_profile_art import SSL, UA
    def read(url):
        with urlopen(Request(url, headers={'User-Agent': UA}), context=SSL, timeout=120) as response:
            return json.load(response)
    data_revision = api('repos/arkpedia/arkpedia-data/commits/main')['sha']
    if not re.fullmatch(r'[a-f0-9]{40}', data_revision):
        raise ValueError('Unpinned content source')
    lock = read(f'https://raw.githubusercontent.com/arkpedia/arkpedia-data/{data_revision}/source/data/upstream.lock.json')['repositories']
    declared = set()
    pictures = set()
    for repository, language in [('Kengxxiao/ArknightsGameData', 'zh_CN'), ('PuppiizSunniiz/ArknightsGameData_YoStar', 'en_US')]:
        commit = lock[repository]['commit']
        if not re.fullmatch(r'[a-f0-9]{40}', commit):
            raise ValueError('Unpinned IS game table')
        table = read(f'https://raw.githubusercontent.com/{repository}/{commit}/{language}/gamedata/excel/roguelike_topic_table.json')
        declared.update(icon_ids(table))
        pictures.update(cg_ids(table))
    snapshots = {}
    for region in ('cn', 'en'):
        commit = api(f'repos/{REPO}/branches/{region}')['commit']['sha']
        entries = []
        for base, folders in [(ART, ART_FOLDERS), (UI, None), (AVG.rsplit('/', 1)[0], {'images'}), (CC, CC_FOLDERS)]:
            listing = api(f'repos/{REPO}/contents/{urllib.parse.quote(base)}?ref={commit}')
            for folder in listing:
                if folder['type'] != 'dir' or (folders and folder['name'] not in folders):
                    continue
                tree = api(f'repos/{REPO}/git/trees/{folder["sha"]}?recursive=1')
                if tree.get('truncated'):
                    raise ValueError(f'Truncated IS asset tree: {folder["path"]}')
                entries.extend({**entry, 'path': folder['path'] + '/' + entry['path']} for entry in tree['tree'])
        snapshots[region] = {'commit': commit, 'tree': entries}
    return snapshots, declared, pictures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-cache', type=Path, help='Previously fetched, immutable native trees and game tables for a local review')
    args = parser.parse_args()
    if args.inventory_cache:
        cache = args.inventory_cache
        snapshots = {}
        declared = set()
        for region in ('cn', 'en'):
            art = json.loads((cache / f'arkpedia-is-art-{region}.json').read_text())
            ui = json.loads((cache / f'arkpedia-is-ui-{region}.json').read_text())
            if art['commit'] != ui['commit']:
                raise ValueError('Mixed IS asset revisions')
            snapshots[region] = {'commit': art['commit'], 'tree': art['tree'] + ui['tree']}
            table = json.loads((cache / f'arkpedia-is-{region}-table.json').read_text())
            declared.update(icon_ids(table))
            pictures.update(cg_ids(table))
    else:
        snapshots, declared, pictures = snapshots_from_upstream()
    wanted = candidates(snapshots, declared, pictures)
    catalogues = {}
    for dest, source_name in SOURCES.items():
        count = sum(target.startswith(dest + '/') for target in wanted)
        # A local review cache predates Contingency Contract art; upstream runs must find it.
        if count < MINIMUM[dest] and (dest == DEST or not args.inventory_cache):
            raise ValueError(f'Incomplete game art inventory under {dest}; preserving published assets')
        source_path = ROOT / source_name
        catalogues[dest] = (source_path, json.loads(source_path.read_text()) if source_path.exists() else {'version': 1, 'repository': REPO, 'assets': {}})
    def catalogue(target):
        return catalogues[CC_DEST if target.startswith(CC_DEST + '/') else DEST][1]
    manifest_path = ROOT / 'asset-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    changed = []
    pending = [(target, source) for target, source in wanted.items() if target not in manifest['files'] or any(catalogue(target)['assets'].get(target, {}).get(key) != source[key] for key in ('sourceRegion', 'sourceBlob'))]
    def download(job):
        target, source = job
        content, (width, height) = convert(fetch(source['sourceCommit'], source['sourcePath']), size_limit(target))
        return target, source, content, width, height
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        for target, source, content, width, height in executor.map(download, pending):
            path = ROOT / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            manifest['files'][target] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(), 'width': width, 'height': height}
            catalogue(target)['assets'][target] = source
            changed.append(target)
    if changed:
        manifest['files'] = dict(sorted(manifest['files'].items()))
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n')
        written = []
        for dest, (source_path, old) in catalogues.items():
            if not any(target.startswith(dest + '/') for target in changed):
                continue
            old['assets'] = dict(sorted(old['assets'].items()))
            source_path.write_text(json.dumps(old, ensure_ascii=False, indent=2) + '\n')
            written += [SOURCES[dest], dest]
        subprocess.run(['git', 'add', '--sparse', '--', 'asset-manifest.json', *written], cwd=ROOT, check=True)
    print(f'IS and CC game art: {len(changed)} files updated; {len(wanted)} native mappings, Global preferred over CN')


if __name__ == '__main__':
    main()
