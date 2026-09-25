import json
from pathlib import Path
import re
import unicodedata
import unittest

ROOT = Path(__file__).resolve().parents[1]
PINNED = re.compile(r'https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/')

def provenance_problems(provenance, manifest, source_map):
    """Everything sources/furniture-reward-icons.json claims that the repository does not bear out.

    A row there names a hand-added file the site asks for by an event reward's name. If the file
    never reached asset-manifest.json it was not published, and the reward renders without an icon
    while the app's completeness check holds the event back. A copyOf row must be the same bytes as
    its original. A source row must pin the commit it came from and stay out of
    asset-source-map.json, whose mirror does not carry furniture art: a map row would either stop
    the daily sync on a missing upstream path or hand the file to the mirror.
    """
    files, problems = manifest['files'], []
    for path, row in provenance['files'].items():
        if unicodedata.normalize('NFC', path) != path:
            problems.append(f'{path}: not NFC, so it is not the name the site asks for')
        if path not in files:
            problems.append(f'{path}: not in asset-manifest.json')
            continue
        if 'copyOf' in row:
            original = files.get(row['copyOf'])
            if not original or original['sha256'] != files[path]['sha256']:
                problems.append(f'{path}: not a byte copy of {row["copyOf"]}')
        elif 'source' in row:
            if not PINNED.match(row['source']) or not re.fullmatch(r'[0-9a-f]{40}', row.get('sourceBlob', '')):
                problems.append(f'{path}: source is not pinned to a commit and blob')
            if path in source_map['files']:
                problems.append(f'{path}: has an asset-source-map.json row')
        else:
            problems.append(f'{path}: neither copyOf nor source')
    return problems

class FurnitureRewardIconTests(unittest.TestCase):
    def test_every_listed_icon_is_published_as_described(self):
        read = lambda name: json.loads((ROOT / name).read_text(encoding='utf-8'))
        self.assertEqual(provenance_problems(read('sources/furniture-reward-icons.json'), read('asset-manifest.json'),
                                             read('asset-source-map.json')), [])

    def test_each_mismatch_is_named(self):
        source = 'https://raw.githubusercontent.com/o/r/' + 'a' * 40 + '/x.png'
        manifest = {'files': {'material-icons/CN.webp': {'sha256': '1'}, 'material-icons/EN.webp': {'sha256': '2'},
                              'material-icons/Mapped.webp': {'sha256': '3'}, 'material-icons/Loose.webp': {'sha256': '4'}}}
        provenance = {'files': {'material-icons/EN.webp': {'copyOf': 'material-icons/CN.webp'},
            'material-icons/Unpublished.webp': {'source': source, 'sourceBlob': 'b' * 40},
            'material-icons/Mapped.webp': {'source': source, 'sourceBlob': 'b' * 40},
            'material-icons/Loose.webp': {'source': source.replace('a' * 40, 'main'), 'sourceBlob': 'b' * 40},
            unicodedata.normalize('NFD', 'material-icons/Café.webp'): {'copyOf': 'material-icons/CN.webp'}}}
        self.assertEqual(provenance_problems(provenance, manifest, {'files': {'material-icons/Mapped.webp': {}}}), [
            'material-icons/EN.webp: not a byte copy of material-icons/CN.webp',
            'material-icons/Unpublished.webp: not in asset-manifest.json',
            'material-icons/Mapped.webp: has an asset-source-map.json row',
            'material-icons/Loose.webp: source is not pinned to a commit and blob',
            unicodedata.normalize('NFD', 'material-icons/Café.webp') + ': not NFC, so it is not the name the site asks for',
            unicodedata.normalize('NFD', 'material-icons/Café.webp') + ': not in asset-manifest.json'])

if __name__ == '__main__':
    unittest.main()
