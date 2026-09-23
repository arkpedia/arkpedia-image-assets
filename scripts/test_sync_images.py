import json
import os
from pathlib import Path
import tempfile
import unittest
from sync_images import discover_operator_assets
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

if __name__ == '__main__':
    unittest.main()
