#!/usr/bin/env python3
"""Extend exact-name image mappings from public game-data and resource snapshots.

Usage: python scripts/build_source_map.py --game-data /path/to/public/excel
       --resource-tree /path/to/github-recursive-tree.json
EN tables: Kengxxiao/ArknightsGameData_YoStar/en_US/gamedata/excel.
Never fuzzy-match names or overwrite an existing reviewed mapping.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def safe(name):
    return name.translate({ord(c): None for c in '\\/*?:"<>|'}).strip()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-data', required=True, type=Path)
    parser.add_argument('--resource-tree', required=True, type=Path)
    args = parser.parse_args()
    read = lambda name: json.loads((args.game_data / f'{name}.json').read_text())
    tree = json.loads(args.resource_tree.read_text())
    if tree.get('truncated'):
        raise ValueError('Incomplete resource tree')
    blobs = {row['path']: row['sha'] for row in tree['tree'] if row['type'] == 'blob'}
    mapping_path = ROOT / 'asset-source-map.json'
    mapping = json.loads(mapping_path.read_text())
    manifest = json.loads((ROOT / 'asset-manifest.json').read_text())['files']
    candidates = {}
    def add(target, source, width):
        if target not in manifest or source not in blobs or target in mapping['files']:
            return
        # Multiple distinct sources for the same display name require review.
        candidates.setdefault(target, set()).add((source, width))
    chars = read('character_table')
    skills = read('skill_table')
    for char in chars.values():
        for skill in char.get('skills') or []:
            entry = skills.get(skill['skillId'])
            if entry and entry.get('levels'):
                source = f'skill/skill_icon_{entry.get("iconId") or skill["skillId"]}.png'
                add(f'skill-icons/{safe(char["name"])} - {safe(entry["levels"][0]["name"])}.webp', source, 128)
    for enemy in read('enemy_handbook_table')['enemyData'].values():
        add(f'enemies-icons/{safe(enemy["name"])}.webp', f'enemy/{enemy["enemyId"]}.png', 128)
    for item in read('item_table')['items'].values():
        # The game's circled icons are 183px; kept at that, never squeezed to 180.
        add(f'material-icons/{safe(item["name"])}.webp', f'item/{item["iconId"]}.png', 183)
    building = read('building_data')
    for char_id, char in building['chars'].items():
        if char_id not in chars:
            continue
        for group in char.get('buffChar', []):
            for buff in group.get('buffData', []):
                entry = building['buffs'][buff['buffId']]
                add(f'base-skill-icons/{safe(chars[char_id]["name"])} - {safe(entry["buffName"])}.webp',
                    f'building_skill/{entry["skillIcon"]}.png', 128)
    for target, sources in candidates.items():
        if len(sources) != 1:
            continue
        source, width = next(iter(sources))
        mapping['files'][target] = {'sourcePath': source, 'sourceBlob': blobs[source], 'maxWidth': width}
    mapping['files'] = dict(sorted(mapping['files'].items()))
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + '\n')
    print(f'{len(mapping["files"])} exact mappings; ambiguous and unknown names preserved for review.')

if __name__ == '__main__':
    main()
