import json
import os
from pathlib import Path
import tempfile
import unittest
from sync_images import discover_enemy_assets, discover_operator_assets
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
                       {'enemies': [{'id': 'enemy_3015_ubstb', 'icon': '/operator-icons/Jailed Student.webp'}]}, {'enemies': [{'icon': '/enemies-icons/Jailed Student.webp'}]}):
            with self.assertRaisesRegex(ValueError, r'enemies/People, A People\.json: '):
                self.discover(None, bundle=bundle)

    def test_a_checkout_without_enemy_records_fails(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'ARKPEDIA_DATA_ROOT': temp}, clear=True):
            with self.assertRaisesRegex(ValueError, r'source/data/enemies is missing'):
                discover_enemy_assets({'files': {}}, STUDENTS, {'files': {}})

if __name__ == '__main__':
    unittest.main()
