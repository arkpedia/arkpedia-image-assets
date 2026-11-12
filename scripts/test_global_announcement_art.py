import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from global_announcement_art import announcement_images
import sync_global_banner_art as sync

DAY = dt.date(2026, 11, 12)
SOURCE = 'https://www.arknights.global/news/5092'
POSTER = 'event-poster/[Side Story – Crossover] Thunder in the Azure Dream.webp'
BANNER = 'headhunting-banner-images/[Crossover] Hunters of the Umbral Wilds.webp'
BASE = 'https://webusstatic.yo-star.com/web-cms-test/upload/content/2026/11/11/'


def fixture(root):
    data = root / 'source/data'
    (data / 'events').mkdir(parents=True)
    (data / 'official-news/global').mkdir(parents=True)
    events = [{'name': '[Side Story – Crossover] Thunder in the Azure Dream', 'poster': '/' + POSTER,
        'global': {'dateRange': '2026/11/26–2026/12/10', 'timingSource': SOURCE}}]
    banners = [{'name': 'Hunters of the Umbral Wilds', 'banner_image': '/' + BANNER,
        'global_date': '2026/11/26–2026/12/10', 'global_date_estimated': False, 'global_window': {'timingSource': SOURCE}}]
    post = {'url': SOURCE, 'title': '[ARKNIGHTS X MONSTER HUNTER] SIDESTORY: THUNDER IN THE AZURE DREAM OPEN',
        'publishTime': 1794452109319,
        'lines': ['01 [ARKNIGHTS X MONSTER HUNTER] SIDESTORY: THUNDER IN THE AZURE DREAM OPEN',
            '02 [ARKNIGHTS X MONSTER HUNTER] LIMITED HEADHUNTING OPEN – HUNTERS OF THE UMBRAL WILDS',
            '03 THUNDER IN THE AZURE DREAM LOGIN REWARDS'],
        'art': [{'url': BASE+'event.png', 'line': 0}, {'url': BASE+'banner.png', 'line': 1}, {'url': BASE+'login.png', 'line': 2}]}
    (data / 'events/events_2026.json').write_text(json.dumps(events))
    (data / 'headhunting_banners.json').write_text(json.dumps(banners))
    (data / 'official-news/global/5092.json').write_text(json.dumps(post))
    return data, post


class AnnouncementArtTests(unittest.TestCase):
    def test_exact_confirming_post_selects_event_and_banner_not_login_art(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); fixture(root)
            found = announcement_images(root, DAY)
            self.assertEqual({target: row['url'] for target,row in found.items()}, {POSTER: BASE+'event.png', BANNER: BASE+'banner.png'})
            self.assertTrue(all(row['sourcePage'] == SOURCE for row in found.values()))
            self.assertEqual(announcement_images(root, DAY + dt.timedelta(days=50)), {})

    def test_ambiguous_or_untrusted_images_do_not_replace_current_art(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); data, post = fixture(root)
            post['art'].append({'url': BASE+'other.png', 'line': 0})
            post['art'][1]['url'] = 'https://example.com/banner.png'
            (data / 'official-news/global/5092.json').write_text(json.dumps(post))
            self.assertEqual(announcement_images(root, DAY), {})

    def test_forecast_and_wrong_notice_are_not_global_art(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); data, post = fixture(root)
            post['url'] = 'https://www.arknights.global/news/5093'
            (data / 'official-news/global/5092.json').write_text(json.dumps(post))
            self.assertEqual(announcement_images(root, DAY), {})
            post['url'] = SOURCE
            (data / 'official-news/global/5092.json').write_text(json.dumps(post))
            file = data/'events/events_2026.json'; events=json.loads(file.read_text());events[0]['global']['note']='Predicted';file.write_text(json.dumps(events))
            file = data/'headhunting_banners.json';banners=json.loads(file.read_text());banners[0]['global_date_estimated']=True;file.write_text(json.dumps(banners))
            self.assertEqual(announcement_images(root, DAY), {})

    def test_official_art_replaces_published_cn_files_without_wiki_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); fixture(root)
            (root/'sources').mkdir()
            (root/'asset-manifest.json').write_text(json.dumps({'files': {POSTER: {}, BANNER: {}}}))
            image=io.BytesIO();Image.new('RGB',(1560,500),'teal').save(image,'PNG');content=image.getvalue()
            with patch.object(sync,'ROOT',root), patch.dict(os.environ,{'ARKPEDIA_DATA_ROOT':str(root)}), \
                 patch.object(sync.dt,'date',wraps=dt.date) as date, patch.object(sync,'fetch',return_value=content), \
                 patch.object(sync,'image_info',side_effect=AssertionError('Wiki must not be required')), patch.object(sync.subprocess,'run') as git, \
                 patch.object(sync.sys,'argv',['sync','--official-only']):
                date.today.return_value=DAY
                sync.main()
                manifest=(root/'asset-manifest.json').read_bytes()
                provenance=json.loads((root/'sources/global-banner-art.json').read_text())
                self.assertEqual(provenance[POSTER]['sourceSha256'],hashlib.sha256(content).hexdigest())
                self.assertEqual(provenance[BANNER]['sourcePage'],SOURCE)
                self.assertTrue((root/POSTER).exists());self.assertTrue((root/BANNER).exists())
                git.reset_mock();sync.main()
                self.assertEqual((root/'asset-manifest.json').read_bytes(),manifest)
                git.assert_not_called()

    def test_non_key_art_keeps_the_published_manifest_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fixture(root)
            manifest=json.dumps({'files':{POSTER:{'sha256':'old'}, BANNER:{'sha256':'old'}}})
            (root/'asset-manifest.json').write_text(manifest)
            image=io.BytesIO();Image.new('RGB',(32,32),'red').save(image,'PNG')
            with patch.object(sync,'ROOT',root),patch.dict(os.environ,{'ARKPEDIA_DATA_ROOT':str(root)}), \
                 patch.object(sync.dt,'date',wraps=dt.date) as date,patch.object(sync,'fetch',return_value=image.getvalue()), \
                 patch.object(sync.sys,'argv',['sync','--official-only']):
                date.today.return_value=DAY
                with self.assertRaisesRegex(ValueError,'not section key art'):
                    sync.main()
            self.assertEqual((root/'asset-manifest.json').read_text(),manifest)
            self.assertFalse((root/POSTER).exists())

if __name__ == '__main__':
    unittest.main()
