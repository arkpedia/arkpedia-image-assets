import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from sync_global_banner_art import jobs, wiki_titles, image_info
from unittest.mock import patch

class GlobalArtTests(unittest.TestCase):
    def test_title_variants_are_only_english(self):
        titles = wiki_titles('[Limited-Time] Rage of The Many')
        self.assertIn('File:EN Rage of the Many banner.png', titles)
        self.assertIn('File:EN Vector Breakthrough Trial from Misery banner.png', wiki_titles('Vector Breakthrough #2: Trial from Misery'))
        self.assertTrue(all(t.startswith('File:EN ') for t in titles))
        self.assertIn('File:EN Stronghold Protocol Alliance Part 2 banner.png', wiki_titles('Stronghold Protocol Alliance 2nd Half'))

    def test_en_preference_is_not_response_order(self):
        response = {'query': {'pages': {'1': {'title': 'File:EN Example banner.png', 'imageinfo': [{'sha1': 'fallback'}]},
            '2': {'title': 'File:EN Example Rerun banner.png', 'imageinfo': [{'sha1': 'preferred'}]}}}}
        with patch('sync_global_banner_art.fetch', return_value=json.dumps(response).encode()):
            self.assertEqual(image_info(wiki_titles('Example Rerun'))[1]['sha1'], 'preferred')

    def test_global_window_and_sparse_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); data = root / 'source/data'; (data / 'events').mkdir(parents=True)
            banners = [{'name': 'CN only', 'cn_date': '2026/09/01–2026/09/30', 'banner_image': '/headhunting-banner-images/cn.webp'},
                {'name': 'Released', 'global_date': '2026/09/16–2026/09/30', 'banner_image': '/headhunting-banner-images/en.webp'},
                {'name': 'Distant', 'global_date': '2026/12/01–2026/12/30', 'banner_image': '/headhunting-banner-images/future.webp'}]
            (data / 'headhunting_banners.json').write_text(json.dumps(banners))
            (data / 'events/events_2026.json').write_text(json.dumps([{'name': 'Event', 'global': {'dateRange': '2026/09/16–2026/09/30'}, 'poster': '/event-poster/event.webp'}]))
            self.assertEqual(list(jobs(root, dt.date(2026, 9, 22))), [('Released', 'headhunting-banner-images/en.webp'), ('Event', 'event-poster/event.webp')])

if __name__ == '__main__':
    unittest.main()
