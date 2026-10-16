import json
import unittest

from validate_images import ROOT, KNOWN_CASE_COLLISIONS, manifest_records, validate_case_inventory


class CaseInventoryTests(unittest.TestCase):
    def test_distinct_paths_need_no_exception(self):
        self.assertEqual(validate_case_inventory(['icons/a.webp', 'icons/b.webp'], {}), 0)

    def test_case_aliases_and_unicode_equivalents_are_rejected(self):
        for paths in [
            ['icons/A.webp', 'icons/a.webp'],
            ['Icons/a.webp', 'icons/a.webp'],
            ['icons/café.webp', 'icons/cafe\u0301.webp'],
        ]:
            with self.subTest(paths=paths), self.assertRaisesRegex(ValueError, 'New case-insensitive'):
                validate_case_inventory(paths, {})

    def test_reviewed_pair_cannot_grow_and_retired_exceptions_must_be_removed(self):
        pair = frozenset({'icons/a.webp', 'icons/A.webp'})
        allowed = {pair: 'Preserve existing aliases until their migration is reviewed.'}
        self.assertEqual(validate_case_inventory(pair, allowed), 1)
        with self.assertRaisesRegex(ValueError, 'Remove resolved'):
            validate_case_inventory(['icons/a.webp'], allowed)
        with self.assertRaisesRegex(ValueError, 'New case-insensitive'):
            validate_case_inventory([*pair, 'ICONS/a.webp'], allowed)
        with self.assertRaisesRegex(ValueError, 'needs a reason'):
            validate_case_inventory(pair, {pair: ''})

    def test_published_inventory_has_only_the_documented_legacy_pair(self):
        records = manifest_records(json.loads((ROOT / 'asset-manifest.json').read_text()))
        self.assertGreater(len(records), 15_000)
        self.assertEqual(validate_case_inventory(records), len(KNOWN_CASE_COLLISIONS))


if __name__ == '__main__':
    unittest.main()
