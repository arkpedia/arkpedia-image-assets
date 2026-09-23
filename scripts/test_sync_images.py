import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import sync_images
from sync_images import discover_enemy_assets, discover_operator_assets, plan_refresh
from PIL import Image
from unittest.mock import patch

BLOBS = {'avatar/char_9001_tok.png': 'a', 'item/p_char_9001_tok.png': 'b'}

class DiscoveryTests(unittest.TestCase):
    def discover(self, total_cost, manifest_files=()):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'source/data/operators-5star'; folder.mkdir(parents=True)
            (folder / 'Tok.json').write_text(json.dumps({'name': 'Tok', 'internalName': 'char_9001_tok', 'rarity': 5,
                'potential': {'totalCost': total_cost}}))
            mapping = {'files': {}}
            # No game tables: discovery must not depend on the runner's environment.
            with patch.dict(os.environ, {'ARKPEDIA_DATA_ROOT': temp}, clear=True):
                added = discover_operator_assets(mapping, BLOBS, {'files': dict.fromkeys(manifest_files, {})})
            return added, mapping

    def test_flat_and_grouped_token_costs_find_the_same_token(self):
        for total_cost in ([{'name': "Tok's Token", 'quantity': 5}], [[{'name': "Tok's Token", 'quantity': 5}]]):
            added, mapping = self.discover(total_cost)
            self.assertIn("material-icons/Tok's Token.webp", added)
            self.assertEqual(mapping['files']["material-icons/Tok's Token.webp"]['sourcePath'], 'item/p_char_9001_tok.png')
        self.assertEqual(self.discover([])[0], ['five-star-icons/Tok - Base.webp'])

    def test_unknown_cost_shape_names_the_record(self):
        for total_cost in ({'name': "Tok's Token"}, ["Tok's Token"], [{'name': "Tok's Token"}, [{'name': "Tok's Token"}]], [[["Tok's Token"]]], None):
            with self.assertRaisesRegex(ValueError, r'operators-5star/Tok\.json: potential\.totalCost'):
                self.discover(total_cost)

    def test_hand_added_art_in_the_manifest_is_never_mapped(self):
        added, mapping = self.discover([{'name': "Tok's Token", 'quantity': 5}], ['five-star-icons/Tok - Base.webp'])
        self.assertEqual(added, ["material-icons/Tok's Token.webp"])
        self.assertNotIn('five-star-icons/Tok - Base.webp', mapping['files'])

STUDENTS = {'enemy/enemy_3015_ubstb.png': 'c', 'enemy/enemy_3016_ubstg.png': 'd', 'enemy/enemy_1587_ubbplwq.png': 'e'}

class EnemyDiscoveryTests(unittest.TestCase):
    def discover(self, enemies, manifest_files=(), blobs=STUDENTS, bundle=None):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'source/data/enemies'; folder.mkdir(parents=True)
            (folder / 'People, A People.json').write_text(json.dumps(bundle if bundle is not None else {'schema_version': 3,
                'content': {'kind': 'event', 'id': 'act51side'}, 'enemies': enemies}))
            mapping = {'files': {}}
            with patch.dict(os.environ, {'ARKPEDIA_DATA_ROOT': temp}, clear=True):
                added = discover_enemy_assets(mapping, blobs, {'files': dict.fromkeys(manifest_files, {})})
            return added, mapping

    def test_the_records_icon_path_is_the_target(self):
        # Two Jailed Students with different art: the record, not the name, says which file is which.
        added, mapping = self.discover([
            {'id': 'enemy_3015_ubstb', 'name': 'Jailed Student', 'icon': '/enemies-icons/Jailed Student.webp'},
            {'id': 'enemy_3016_ubstg', 'name': 'Jailed Student', 'icon': '/enemies-icons/Jailed Student (STU2).webp'},
        ])
        self.assertEqual(added, ['enemies-icons/Jailed Student.webp', 'enemies-icons/Jailed Student (STU2).webp'])
        self.assertEqual(mapping['files']['enemies-icons/Jailed Student (STU2).webp'],
                         {'sourcePath': 'enemy/enemy_3016_ubstg.png', 'maxWidth': 128})

    def test_null_icons_listed_targets_and_absent_sources_are_skipped(self):
        added, mapping = self.discover([
            {'id': 'enemy_3009_mpprss', 'name': 'EYESOFPRIESTESS', 'icon': None},
            {'id': 'enemy_3015_ubstb', 'name': 'Jailed Student', 'icon': '/enemies-icons/Jailed Student.webp'},
            {'id': 'enemy_9999_new', 'name': 'Not Mirrored Yet', 'icon': '/enemies-icons/Not Mirrored Yet.webp'},
            {'id': 'enemy_1587_ubbplwq', 'name': 'Pavlovich, Magistrate', 'icon': '/enemies-icons/Pavlovich, Magistrate.webp'},
        ], ['enemies-icons/Jailed Student.webp'])
        self.assertEqual(added, ['enemies-icons/Pavlovich, Magistrate.webp'])
        self.assertEqual(list(mapping['files']), added)

    def test_a_shared_name_maps_once_and_different_art_under_it_fails(self):
        same = {**STUDENTS, 'enemy/enemy_3016_ubstg.png': 'c'}
        shared = [{'id': 'enemy_3016_ubstg', 'icon': '/enemies-icons/Jailed Student.webp'},
                  {'id': 'enemy_3015_ubstb', 'icon': '/enemies-icons/Jailed Student.webp'}]
        added, mapping = self.discover(shared, blobs=same)
        self.assertEqual(mapping['files'], {'enemies-icons/Jailed Student.webp': {'sourcePath': 'enemy/enemy_3015_ubstb.png', 'maxWidth': 128}})
        with self.assertRaisesRegex(ValueError, r'Jailed Student\.webp: enemies enemy_3015_ubstb, enemy_3016_ubstg'):
            self.discover(shared)

    def test_unreadable_records_name_the_file(self):
        for bundle in ([], {'enemies': {}}, {'enemies': ['enemy_3015_ubstb']}, {'enemies': [{'id': 'enemy_3015_ubstb', 'icon': 'enemies-icons/Jailed Student.webp'}]},
                       {'enemies': [{'id': 'enemy_3015_ubstb', 'icon': '/operator-icons/Jailed Student.webp'}]}, {'enemies': [{'icon': '/enemies-icons/Jailed Student.webp'}]},
                       {'enemies': [{'id': 'enemy_3015_ubstb', 'icon': '/enemies-icons/Jailed Student.png'}]}):
            with self.assertRaisesRegex(ValueError, r'enemies/People, A People\.json: '):
                self.discover(None, bundle=bundle)

    def test_a_checkout_without_enemy_records_fails(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'ARKPEDIA_DATA_ROOT': temp}, clear=True):
            with self.assertRaisesRegex(ValueError, r'source/data/enemies is missing'):
                discover_enemy_assets({'files': {}}, STUDENTS, {'files': {}})

TOKEN = "material-icons/Tok's Token.webp"
GROMOV, STUDENT = 'enemies-icons/Gromov.webp', 'enemies-icons/Jailed Student.webp'

class RefreshPlanTests(unittest.TestCase):
    def plan(self, rows, listed=()):
        mapping = {'files': rows}
        jobs, adopted = plan_refresh(mapping, BLOBS, {'files': dict.fromkeys(listed, {})}, 'rev')
        return [job[0] for job in jobs], adopted, mapping['files']

    def test_a_listed_file_without_a_blob_is_adopted_not_fetched(self):
        # The row publish-catalogue-assets.py writes in the same commit as the file and
        # its manifest row, and the row a reviewer writes for a file added by hand.
        jobs, adopted, rows = self.plan({TOKEN: {'sourcePath': 'item/p_char_9001_tok.png', 'maxWidth': 180}}, [TOKEN])
        self.assertEqual((jobs, adopted), ([], [TOKEN]))
        self.assertEqual(rows[TOKEN], {'sourcePath': 'item/p_char_9001_tok.png', 'maxWidth': 180, 'sourceBlob': 'b'})

    def test_an_unlisted_file_without_a_blob_is_fetched(self):
        jobs, adopted, rows = self.plan({TOKEN: {'sourcePath': 'item/p_char_9001_tok.png', 'maxWidth': 180}})
        self.assertEqual((jobs, adopted), ([TOKEN], []))
        self.assertNotIn('sourceBlob', rows[TOKEN])

    def test_a_synced_file_is_fetched_only_when_upstream_changes(self):
        # Listed or not, a row with a blob belongs to the mirror.
        for blob, expected in (('b', []), ('old', [TOKEN])):
            jobs, adopted, _ = self.plan({TOKEN: {'sourcePath': 'item/p_char_9001_tok.png', 'sourceBlob': blob}}, [TOKEN])
            self.assertEqual((jobs, adopted), (expected, []))

    def test_a_source_gone_upstream_fails_even_for_a_listed_file(self):
        with self.assertRaisesRegex(ValueError, r'Upstream removed item/p_char_9002_gone\.png'):
            self.plan({TOKEN: {'sourcePath': 'item/p_char_9002_gone.png'}}, [TOKEN])

class RefreshRunTests(unittest.TestCase):
    def test_a_run_keeps_a_listed_file_and_fetches_the_rest(self):
        # The 09-23 repro: a hand-added icon at a mapped target the sync has never
        # fetched was replaced by the upstream image on the next run.
        buffer = io.BytesIO(); Image.new('RGBA', (256, 256), (0, 128, 255, 255)).save(buffer, 'PNG'); png = buffer.getvalue()
        blob = hashlib.sha1(b'blob %d\0' % len(png) + png).hexdigest()
        revision = 'f' * 40
        tree = {'truncated': False, 'tree': [{'path': f'enemy/{name}.png', 'type': 'blob', 'sha': blob}
                                             for name in ('enemy_1587_ubbplwq', 'enemy_3015_ubstb')]}
        hand = b'reviewed bytes added by hand'
        rows = {GROMOV: {'sourcePath': 'enemy/enemy_1587_ubbplwq.png', 'maxWidth': 128},
                STUDENT: {'sourcePath': 'enemy/enemy_3015_ubstb.png', 'maxWidth': 128}}
        listed = {GROMOV: {'bytes': len(hand), 'sha256': hashlib.sha256(hand).hexdigest()}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'enemies-icons').mkdir()
            (root / GROMOV).write_bytes(hand)
            (root / 'asset-manifest.json').write_text(json.dumps({'files': listed}))
            (root / 'asset-source-map.json').write_text(json.dumps({'files': rows}))
            api = lambda path: {'sha': revision} if path.endswith('/commits/main') else tree
            with patch('sync_images.ROOT', root), patch('sync_images.api', side_effect=api), \
                    patch('sync_images.fetch', return_value=png) as fetch, patch('sync_images.subprocess.run') as run, \
                    patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()) as out:
                sync_images.main()
            fetch.assert_called_once_with('enemy/enemy_3015_ubstb.png', revision)
            self.assertEqual((root / GROMOV).read_bytes(), hand)
            manifest = json.loads((root / 'asset-manifest.json').read_text())['files']
            self.assertEqual(manifest[GROMOV], listed[GROMOV])
            self.assertEqual((manifest[STUDENT]['width'], manifest[STUDENT]['height']), (128, 128))
            mapping = json.loads((root / 'asset-source-map.json').read_text())['files']
            self.assertEqual({asset: row['sourceBlob'] for asset, row in mapping.items()}, {GROMOV: blob, STUDENT: blob})
            # Only the fetched image is staged besides the two JSON files.
            self.assertEqual(run.call_args_list[0].args[0], ['git', 'add', '--sparse', '--', STUDENT])
            self.assertIn('adopted 1 listed files; refreshed 1 images', out.getvalue())

if __name__ == '__main__':
    unittest.main()
