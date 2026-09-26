"""The operators job reads its game tables at the commits the content release pinned (OR-11)."""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import upstream_tables

ROOT = Path(__file__).resolve().parents[1]

# arkpedia-data's source/data/upstream.lock.json as the 2026-09-25 release published it.
LOCK = {
    'version': 1,
    'repositories': {
        'Kengxxiao/ArknightsGameData': {'branch': 'master', 'commit': 'bb8f9ac8db143a661577ed6ef5184d3c6e93d1d0'},
        'ArknightsAssets/ArknightsGamedata': {'branch': 'master', 'commit': '1bab58e6d70b7b12db9c0afffadd75b07b9307a8'},
        'yuanyan3060/ArknightsGameResource': {'branch': 'main', 'commit': 'bb71653fcafc46130f70c6eec3d383888f670573'},
        'PuppiizSunniiz/ArknightsGameData_YoStar': {'branch': 'main', 'commit': '65240c58eb0c86cb74de28bc9ef9cf8b7c6cf38e'},
    },
    'cnTables': {'repository': 'Kengxxiao/ArknightsGameData', 'commit': 'bb8f9ac8db143a661577ed6ef5184d3c6e93d1d0',
                 'folder': 'zh_CN/gamedata', 'serialization': 'named'},
}
EN = 'https://raw.githubusercontent.com/ArknightsAssets/ArknightsGamedata/1bab58e6d70b7b12db9c0afffadd75b07b9307a8/en/gamedata/excel'
CN = 'https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/bb8f9ac8db143a661577ed6ef5184d3c6e93d1d0/zh_CN/gamedata/excel'
# A raw file address at a branch rather than a commit: its bytes change under the reader.
BRANCH_ADDRESS = re.compile(r'raw\.githubusercontent\.com/[^/\s"\']+/[^/\s"\']+/(?:main|master)/')


class PinnedTables(unittest.TestCase):
    def test_every_table_comes_from_the_mirror_and_commit_the_release_read(self):
        self.assertEqual(upstream_tables.table_urls(LOCK), {
            'building-en.json': f'{EN}/building_data.json',
            'character_table-en.json': f'{EN}/character_table.json',
            'skill_table-en.json': f'{EN}/skill_table.json',
            'building-cn.json': f'{CN}/building_data.json',
            'character_table-cn.json': f'{CN}/character_table.json',
            'skill_table-cn.json': f'{CN}/skill_table.json',
        })

    def test_the_cn_tables_follow_the_mirror_the_release_settled_on(self):
        lock = copy.deepcopy(LOCK)
        lock['cnTables'] = {'repository': 'yuanyan3060/ArknightsGameResource', 'commit': 'bb71653fcafc46130f70c6eec3d383888f670573',
                            'folder': 'gamedata', 'serialization': 'numeric'}
        self.assertEqual(upstream_tables.table_urls(lock)['skill_table-cn.json'],
                         'https://raw.githubusercontent.com/yuanyan3060/ArknightsGameResource/bb71653fcafc46130f70c6eec3d383888f670573/gamedata/excel/skill_table.json')
        # A lock from before cnTables: Kengxxiao at its own pin.
        del lock['cnTables']
        self.assertEqual(upstream_tables.table_urls(lock)['building-cn.json'], f'{CN}/building_data.json')

    def test_a_lock_without_a_commit_fails_instead_of_reading_a_branch(self):
        for mutate, message in [
            (lambda lock: lock['repositories']['ArknightsAssets/ArknightsGamedata'].update(commit=None), 'ArknightsAssets/ArknightsGamedata'),
            (lambda lock: lock['repositories'].pop('ArknightsAssets/ArknightsGamedata'), 'ArknightsAssets/ArknightsGamedata'),
            (lambda lock: lock['cnTables'].update(commit='master'), 'cnTables'),
            (lambda lock: lock['cnTables'].update(folder='gamedata'), 'cnTables'),
            (lambda lock: (lock.pop('cnTables'), lock['repositories']['Kengxxiao/ArknightsGameData'].update(commit=None)), 'Kengxxiao'),
        ]:
            lock = copy.deepcopy(LOCK)
            mutate(lock)
            with self.assertRaisesRegex(ValueError, message):
                upstream_tables.table_urls(lock)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'upstream.lock.json'
            path.write_text(json.dumps({'version': 2, 'repositories': {}}))
            with self.assertRaisesRegex(ValueError, 'not a version 1 upstream lock'):
                upstream_tables.read_lock(path)

    def test_no_workflow_or_script_reads_a_mirror_at_a_branch(self):
        offenders = []
        for path in sorted([*(ROOT / '.github/workflows').glob('*.yml'), *(ROOT / 'scripts').glob('*.py')]):
            if path.name.startswith('test_'):
                continue
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if BRANCH_ADDRESS.search(line):
                    offenders.append(f'{path.relative_to(ROOT)}:{number}: {line.strip()}')
        self.assertEqual(offenders, [])
        self.assertTrue(BRANCH_ADDRESS.search('https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/excel/x.json'))
        self.assertIsNone(BRANCH_ADDRESS.search(f'{EN}/building_data.json'))

    def test_the_operators_job_loads_its_tables_from_the_lock_it_checks_out(self):
        workflow = (ROOT / '.github/workflows/sync-images.yml').read_text()
        self.assertIn('python scripts/upstream_tables.py "$RUNNER_TEMP/arkpedia-data/source/data/upstream.lock.json" "$RUNNER_TEMP"', workflow)
        # The sync step's environment names exactly the files the loader writes.
        named = set(re.findall(r'\$\{\{ runner\.temp \}\}/([\w-]+\.json)', workflow))
        self.assertEqual(named, set(upstream_tables.table_urls(LOCK)))


if __name__ == '__main__':
    unittest.main()
