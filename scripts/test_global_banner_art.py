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
        # The colon form stays first: the first title the wiki has wins.
        self.assertEqual(wiki_titles('Duel Channel: Ivy Vine')[:2], ['File:EN Duel Channel: Ivy Vine banner.png', 'File:EN Duel Channel Ivy Vine banner.png'])

    def test_en_preference_is_not_response_order(self):
        response = {'query': {'pages': {'1': {'title': 'File:EN Example banner.png', 'imageinfo': [{'sha1': 'fallback'}]},
            '2': {'title': 'File:EN Example Rerun banner.png', 'imageinfo': [{'sha1': 'preferred'}]}}}}
        with patch('sync_global_banner_art.fetch', return_value=json.dumps(response).encode()):
            self.assertEqual(image_info(wiki_titles('Example Rerun'))[1]['sha1'], 'preferred')

    def test_moved_upload_is_found_through_its_redirect(self):
        # The API's answer with `redirects` for a moved EN upload: pages is keyed by the
        # target title, and an underscored title is normalized before it is redirected.
        response = {'batchcomplete': '', 'query': {
            'normalized': [{'from': 'File:EN_Anchor_in_the_Deep_banner.png', 'to': 'File:EN Anchor in the Deep banner.png'}],
            'redirects': [{'from': 'File:EN Anchor in the Deep banner.png', 'to': 'File:EN Anchor In The Deep banner.png'}],
            'pages': {'52000': {'pageid': 52000, 'ns': 6, 'title': 'File:EN Anchor In The Deep banner.png', 'imagerepository': 'local',
                'imageinfo': [{'url': 'https://arknights.wiki.gg/images/EN_Anchor_In_The_Deep_banner.png?573525', 'sha1': '57352557c7306e27b083218cd5691db1cdacdb17'}]}}}}
        for title in ('File:EN Anchor in the Deep banner.png', 'File:EN_Anchor_in_the_Deep_banner.png'):
            with patch('sync_global_banner_art.fetch', return_value=json.dumps(response).encode()) as fetch:
                # The requested title is kept, so sources/global-banner-art.json does not churn.
                self.assertEqual(image_info(['File:EN Missing banner.png', title]), (title, response['query']['pages']['52000']['imageinfo'][0]))
            self.assertIn('redirects=1', fetch.call_args.args[0])

    def test_global_window_and_sparse_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); data = root / 'source/data'; (data / 'events').mkdir(parents=True)
            banners = [{'name': 'CN only', 'cn_date': '2026/09/01–2026/09/30', 'banner_image': '/headhunting-banner-images/cn.webp'},
                {'name': 'Released', 'global_date': '2026/09/16–2026/09/30', 'banner_image': 'https://raw.githubusercontent.com/arkpedia/arkpedia-image-assets/' + 'a'*40 + '/headhunting-banner-images/en%20art.webp'},
                {'name': 'Distant', 'global_date': '2026/12/01–2026/12/30', 'banner_image': '/headhunting-banner-images/future.webp'}]
            (data / 'headhunting_banners.json').write_text(json.dumps(banners))
            (data / 'events/events_2026.json').write_text(json.dumps([{'name': 'Event', 'global': {'dateRange': '2026/09/16–2026/09/30'}, 'poster': '/event-poster/event.webp'}]))
            self.assertEqual(list(jobs(root, dt.date(2026, 9, 22))), [('Released', 'headhunting-banner-images/en art.webp'), ('Event', 'event-poster/event.webp')])

if __name__ == '__main__':
    unittest.main()
