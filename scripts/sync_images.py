#!/usr/bin/env python3
"""Refresh reviewed image mappings directly from a public game-resource mirror.

Never delete assets or guess a renamed source. Unmapped/manual artwork stays intact.
The source map records exact upstream paths and Git blob IDs for incremental updates.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REPO = 'yuanyan3060/ArknightsGameResource'

RARITY_FOLDERS = {
    1: 'one-star-icons',
    2: 'two-star-icons',
    3: 'three-star-icons',
    4: 'four-star-icons',
    5: 'five-star-icons',
    6: 'six-star-icons',
}

def safe_name(value):
    return re.sub(r'[\\/*?:"<>|]', '', value).strip()


def load_building_tables():
    """Load EN first and CN second so released names use Global data.

    Base-skill image filenames are not derived from character or skill IDs. The
    game's building table is the only stable join from a character's base-skill
    slots to the corresponding ``building_skill/*.png`` files. CN is a fallback
    for operators whose art exists before their Global data is published.
    """
    tables = []
    for variable in ('ARKPEDIA_EN_BUILDING_DATA', 'ARKPEDIA_CN_BUILDING_DATA'):
        value = os.environ.get(variable)
        if not value:
            continue
        path = Path(value)
        if not path.is_file():
            raise ValueError(f'{variable} does not point to a file: {path}')
        tables.append(json.loads(path.read_text()))
    return tables


def load_skill_tables():
    """Load (character_table, skill_table) pairs, EN first and CN second.

    A skill icon is not always ``skill_icon_skchr_<slug>_<n>``: the shared generic
    skills every low-rarity operator carries -- "ATK Up γ", "Support γ" -- use a common
    icon (``skcom_atk_up[3]``, ``skcom_assist_cost[3]``). Guessing the character-specific
    name for those finds nothing in the mirror and the icon is silently never mapped.
    The character table names each slot's skillId and the skill table names its icon;
    that join is the only reliable one, and it is what build_source_map.py already uses.
    """
    tables = []
    for region in ('EN', 'CN'):
        chars_var, skills_var = f'ARKPEDIA_{region}_CHARACTER_TABLE', f'ARKPEDIA_{region}_SKILL_TABLE'
        chars_path, skills_path = os.environ.get(chars_var), os.environ.get(skills_var)
        if not chars_path and not skills_path:
            continue
        if not (chars_path and skills_path):
            raise ValueError(f'{chars_var} and {skills_var} must be set together')
        for variable, value in ((chars_var, chars_path), (skills_var, skills_path)):
            if not Path(value).is_file():
                raise ValueError(f'{variable} does not point to a file: {value}')
        tables.append((json.loads(Path(chars_path).read_text()), json.loads(Path(skills_path).read_text())))
    return tables


def skill_icon_source(character_id, index, slug, tables):
    """Upstream path for an operator's ``index``-th (1-based) skill icon.

    Resolves through the first table that knows the character; falls back to the
    character-specific naming convention when no table does, which keeps the old
    behaviour for a brand-new operator the tables have not caught up with.
    """
    for chars, skills in tables:
        slots = (chars.get(character_id) or {}).get('skills') or []
        if index - 1 >= len(slots):
            continue
        skill_id = slots[index - 1].get('skillId')
        if not skill_id:
            continue
        icon = (skills.get(skill_id) or {}).get('iconId') or skill_id
        return f'skill/skill_icon_{icon}.png'
    return f'skill/skill_icon_skchr_{slug}_{index}.png'


def base_skill_sources(character_id, expected_count, tables):
    """Return ordered upstream icon IDs when one table matches every slot."""
    for table in tables:
        character = table.get('chars', {}).get(character_id)
        if not character:
            continue
        entries = []
        for slot in character.get('buffChar') or []:
            data = slot.get('buffData') if isinstance(slot, dict) else None
            if isinstance(data, list):
                entries.extend(row for row in data if isinstance(row, dict) and row.get('buffId'))
            elif isinstance(data, dict) and data.get('buffId'):
                entries.append(data)
        icons = [table.get('buffs', {}).get(row['buffId'], {}).get('skillIcon') for row in entries]
        if len(icons) == expected_count and all(icons):
            return icons
    return []


def potential_costs(operator, operator_path):
    """Return the ``{name, quantity}`` rows of an operator's ``potential.totalCost``.

    Two shapes are in the public data: flat ``[{name, quantity}]``, as generated
    records store it, and grouped ``[[{name, quantity}]]``, as hand-written records
    following the website's ``CostGroup[]`` type store it. Any other shape is a
    schema change this script cannot read, so it fails naming the record rather
    than guessing -- or crashing on ``.get()`` with no hint of which file it was.
    """
    potential = operator.get('potential', {})
    found = potential.get('totalCost', []) if isinstance(potential, dict) else potential
    costs = found if isinstance(potential, dict) and isinstance(found, list) else None
    if costs is not None and all(isinstance(group, list) for group in costs):
        costs = [cost for group in costs for cost in group]
    if costs is None or not all(isinstance(cost, dict) and isinstance(cost.get('name', ''), str) for cost in costs):
        raise ValueError(f'{operator_path}: potential.totalCost must be [{{name, quantity}}] or '
                         f'[[{{name, quantity}}]], found {json.dumps(found, ensure_ascii=False)[:120]}')
    return costs


def discover_operator_assets(mapping, blobs, manifest):
    """Add predictable operator media from Arkpedia's public data checkout.

    The old updater only refreshed reviewed paths already present in the source
    map. That made every new operator require a manual map edit even when the
    public data had its stable character ID and the resource mirror already had
    the matching portraits, token, and skill icons.

    A target already listed in the asset manifest but absent from the source map
    was added by hand (a capture, a correction, art published before the mirror
    had it). It is never mapped here: mapping it would re-fetch and re-encode it
    over the reviewed file. Such a file joins the map only by review, with its
    current upstream blob recorded so nothing is rewritten: build_source_map.py
    for skill, base-skill and material icons, a manual map row for portraits.
    """
    data_root = os.environ.get('ARKPEDIA_DATA_ROOT')
    if not data_root:
        print('ARKPEDIA_DATA_ROOT is unset; skipping new operator asset discovery.')
        return []
    data_root = Path(data_root)
    added = []
    building_tables = load_building_tables()
    skill_tables = load_skill_tables()
    for directory in sorted((data_root / 'source' / 'data').glob('operators-*star')):
        for operator_path in sorted(directory.glob('*.json')):
            operator = json.loads(operator_path.read_text())
            name = safe_name(operator.get('name', ''))
            character_id = operator.get('internalName')
            rarity = operator.get('rarity')
            folder = RARITY_FOLDERS.get(rarity)
            if not name or not character_id or not folder:
                continue

            candidates = [
                (f'{folder}/{name} - Base.webp', f'avatar/{character_id}.png', 180),
                (f'{folder}/{name} - Elite 2.webp', f'avatar/{character_id}_2.png', 180),
            ]
            slug = character_id.rsplit('_', 1)[-1]
            for index, skill in enumerate(operator.get('skills', {}).get('skillList', []), 1):
                skill_name = safe_name(skill.get('name', ''))
                if skill_name:
                    candidates.append((
                        f'skill-icons/{name} - {skill_name}.webp',
                        skill_icon_source(character_id, index, slug, skill_tables),
                        128,
                    ))
            base_skills = operator.get('baseSkills', [])
            source_icons = base_skill_sources(character_id, len(base_skills), building_tables)
            raw_operator_name = safe_name(operator.get('rawName') or operator.get('name', ''))
            for base_skill, source_icon in zip(base_skills, source_icons):
                skill_name = safe_name(base_skill.get('rawName') or base_skill.get('name', ''))
                if skill_name:
                    candidates.append((
                        f'base-skill-icons/{raw_operator_name} - {skill_name}.webp',
                        f'building_skill/{source_icon}.png',
                        128,
                    ))
            for cost in potential_costs(operator, operator_path):
                token_name = safe_name(cost.get('name', ''))
                if token_name:
                    target = f'material-icons/{token_name}.webp'
                    sources = (f'item/p_{character_id}.png', f'item/voucher_{slug}.png', f'item/voucher_full_{slug}.png')
                    source = next((candidate for candidate in sources if candidate in blobs), sources[0])
                    candidates.append((target, source, 180))

            for target, source, max_width in candidates:
                if target in mapping['files'] or target in manifest['files'] or source not in blobs:
                    continue
                mapping['files'][target] = {'sourcePath': source, 'maxWidth': max_width}
                added.append(target)
    return added

def api(path):
    last_error = None
    for attempt in range(3):
        try:
            return json.loads(subprocess.check_output(['gh', 'api', path]))
        except (subprocess.CalledProcessError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise last_error

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
    discovered = discover_operator_assets(mapping, blobs, manifest)
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
    print(f'Discovered {len(discovered)} operator assets; checked {len(mapping["files"])} mappings; refreshed {len(changed)} images from {revision}.')

if __name__ == '__main__':
    main()
