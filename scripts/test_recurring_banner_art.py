import contextlib
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from PIL import Image
import sync_recurring_banner_art
from sync_recurring_banner_art import card_jobs, client_card_art, image_info, place_client_cards, rows, wikitext
from unittest.mock import patch

# The API's answer (HTTP 200) for Headhunting/Banners/2027 on 2026-09-23, before the page existed.
MISSING = json.loads('{"error":{"code":"missingtitle","info":"The page you specified doesn\'t exist.","*":"See https://arknights.wiki.gg/api.php for API usage. Subscribe to the mediawiki-api-announce mailing list at &lt;https://lists.wikimedia.org/postorius/lists/mediawiki-api-announce.lists.wikimedia.org/&gt; for notice of API deprecations and breaking changes."}}')
PAGE = {'parse': {'title': 'Headhunting/Banners/2026', 'wikitext': {'*': '{{Banners cell\n|type = standard\n|no = 175\n'
    '|start = 2026/09/11 04:00:00\n|end = 2026/09/25 03:59:59\n|operators = A, B, C, D, E}}'}}}
# The API's answer for Headhunting/Banners/Former-2020, which the wiki moved to .../2020, without `redirects`.
# With `redirects` a double redirect answers the same way.
REDIRECT = {'parse': {'title': 'Headhunting/Banners/Former-2020', 'pageid': 116569, 'wikitext': {'*': '#REDIRECT [[Headhunting/Banners/2020]]'}}}
# The same shape with `redirects` followed: parse names the redirect and returns the target's wikitext.
FOLLOWED = {'parse': {**PAGE['parse'], 'redirects': [{'from': 'Headhunting/Banners/2026', 'to': 'Headhunting/Banners/Global 2026'}]}}

class YearlyPageTests(unittest.TestCase):
    def test_missing_yearly_page_has_no_rows_in_january(self):
        for today in (dt.date(2027, 1, 1), dt.date(2027, 1, 31)):
            with patch('sync_recurring_banner_art.fetch', return_value=MISSING) as fetch:
                self.assertEqual(list(rows(wikitext(today))), [])
            self.assertEqual(fetch.call_args.args[0]['page'], 'Headhunting/Banners/2027')
            self.assertEqual(fetch.call_args.args[0]['redirects'], 1)

    def test_missing_yearly_page_fails_after_january(self):
        # A page moved, renamed or never made would otherwise read as "current" all year.
        for today in (dt.date(2027, 2, 1), dt.date(2027, 6, 1), dt.date(2027, 12, 31)):
            with patch('sync_recurring_banner_art.fetch', return_value=MISSING), \
                    self.assertRaisesRegex(ValueError, r'Headhunting/Banners/2027 does not exist.*missingtitle'):
                wikitext(today)

    def test_other_api_errors_still_fail(self):
        for today in (dt.date(2026, 1, 10), dt.date(2026, 9, 23)):
            for error in ({'code': 'ratelimited', 'info': "You've exceeded your rate limit."}, {'code': 'invalidtitle', 'info': 'Bad title.'}):
                with patch('sync_recurring_banner_art.fetch', return_value={'error': error}), self.assertRaisesRegex(ValueError, error['code']):
                    wikitext(today)

    def test_existing_page_yields_its_rows(self):
        for today in (dt.date(2026, 1, 10), dt.date(2026, 9, 23)):
            for payload in (PAGE, FOLLOWED):
                with patch('sync_recurring_banner_art.fetch', return_value=payload) as fetch:
                    self.assertEqual(list(rows(wikitext(today))), [('standard', '175', dt.date(2026, 9, 11), dt.date(2026, 9, 25))])
                self.assertEqual(fetch.call_args.args[0]['page'], 'Headhunting/Banners/2026')
                # A moved page leaves a redirect, not missingtitle; the API follows it only when asked.
                self.assertEqual(fetch.call_args.args[0]['redirects'], 1)

    def test_unfollowed_redirect_fails_in_any_month(self):
        # '#REDIRECT [[...]]' has no rows, so it would read as current all year.
        for today in (dt.date(2027, 1, 10), dt.date(2027, 6, 1)):
            for text in ('#REDIRECT [[Headhunting/Banners/2020]]', '\n#redirect [[Headhunting/Banners/2020]]'):
                payload = {'parse': {**REDIRECT['parse'], 'wikitext': {'*': text}}}
                with patch('sync_recurring_banner_art.fetch', return_value=payload), \
                        self.assertRaisesRegex(ValueError, r'Headhunting/Banners/2027 is a redirect.*Headhunting/Banners/2020'):
                    wikitext(today)

    def test_image_lookup_follows_redirects(self):
        # The API's answer for a moved EN upload with `redirects`: pages is keyed by the target.
        response = {'batchcomplete': '', 'query': {'redirects': [{'from': 'File:EN Kernel Locating 10 banner.png', 'to': 'File:EN CCB4 Kernel Locating 10.png'}],
            'pages': {'124297': {'pageid': 124297, 'ns': 6, 'title': 'File:EN CCB4 Kernel Locating 10.png', 'imagerepository': 'local',
            'imageinfo': [{'url': 'https://arknights.wiki.gg/images/EN_CCB4_Kernel_Locating_10.png?2a5946', 'sha1': '2a59468c658411e44154ce70b09ba08857cdd69b'}]}}}}
        with patch('sync_recurring_banner_art.fetch', return_value=response) as fetch:
            self.assertEqual(image_info('File:EN Kernel Locating 10 banner.png')['sha1'], '2a59468c658411e44154ce70b09ba08857cdd69b')
        self.assertEqual(fetch.call_args.args[0]['redirects'], 1)

    def run_main(self, today, payload=MISSING):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as data:
            root = Path(temp); manifest = '{"files":{}}\n'
            (root / 'asset-manifest.json').write_text(manifest)
            (Path(data) / 'source/data').mkdir(parents=True)
            (Path(data) / 'source/data/headhunting_banners.json').write_text('[]')
            out = io.StringIO()
            with patch('sync_recurring_banner_art.ROOT', root), patch('sync_recurring_banner_art.utc_today', return_value=today), \
                    patch.dict(os.environ, {'ARKPEDIA_DATA_ROOT': data}), \
                    patch('sync_recurring_banner_art.fetch', return_value=payload) as fetch, contextlib.redirect_stdout(out):
                try:
                    sync_recurring_banner_art.main()
                finally:
                    # One call: no image lookups, no downloads, nothing written or staged.
                    self.assertEqual(fetch.call_count, 1)
                    self.assertEqual((root / 'asset-manifest.json').read_text(), manifest)
                    self.assertEqual(sorted(p.name for p in root.iterdir()), ['asset-manifest.json'])
            return out.getvalue()

    def test_run_before_the_page_exists_is_current_in_january(self):
        self.assertEqual(self.run_main(dt.date(2027, 1, 5)), 'Recurring banner art is current.\n')

    def test_run_without_the_page_after_january_fails(self):
        with self.assertRaisesRegex(ValueError, r'Headhunting/Banners/2027 does not exist'):
            self.run_main(dt.date(2027, 6, 1))

    def test_run_on_an_unfollowed_redirect_fails(self):
        # Before this check the run printed 'Recurring banner art is current.' and exited 0.
        with self.assertRaisesRegex(ValueError, r'Headhunting/Banners/2027 is a redirect'):
            self.run_main(dt.date(2027, 6, 1), REDIRECT)


def banner(name, pool, start, end, kind='standard', image=None):
    return {'name': name, 'pull_type': kind, 'globalPoolId': pool, 'banner_image': image or f"/headhunting-banner-images/{name.replace('#', '')}.webp",
        'global_window': {'startAt': f'{start}T11:00:00.000Z', 'endAt': f'{end}T11:00:00.000Z'}}


def card_png(size=(467, 239), margin=19, color=(200, 40, 40)):
    """A card shaped like the client's: opaque, in a soft transparent margin."""
    image = Image.new('RGBA', size, (0, 0, 0, 0))
    image.paste(Image.new('RGBA', (size[0] - 2 * margin, size[1] - 40), color + (255,)), (margin, 0))
    out = io.BytesIO(); image.save(out, 'PNG')
    return out.getvalue()


class ClientCardTests(unittest.TestCase):
    TODAY = dt.date(2026, 10, 1)

    def jobs(self, banners):
        with tempfile.TemporaryDirectory() as data:
            (Path(data) / 'source/data').mkdir(parents=True)
            (Path(data) / 'source/data/headhunting_banners.json').write_text(json.dumps(banners))
            return list(card_jobs(Path(data), self.TODAY))

    def test_recorded_recurring_banners_near_today_are_the_jobs(self):
        self.assertEqual(self.jobs([
            banner('Standard Pool #177 (Global)', 'DOUBLE_EN_41_0_9', '2026-10-09', '2026-10-23'),
            banner('Kernel #63 (Global)', 'CLASSIC_DOUBLE_EN_41_0_4', '2026-10-06', '2026-10-20', 'kernel'),
            # Too far ahead, long over, not recurring, or no pool to find the card by.
            banner('Standard Pool #179 (Global)', 'DOUBLE_EN_42_0_1', '2026-11-06', '2026-11-20'),
            banner('Standard Pool #150 (Global)', 'DOUBLE_EN_35_0_5', '2025-08-01', '2025-08-15'),
            banner('[Limited] Something', 'LIMITED_41_0_1', '2026-10-01', '2026-10-15', 'limited'),
            {**banner('Standard Pool #176 (Global)', None, '2026-09-25', '2026-10-09'), 'globalPoolId': None},
        ]), [('Standard Pool #177 (Global)', 'DOUBLE_EN_41_0_9', 'headhunting-banner-images/Standard Pool 177 (Global).webp'),
             ('Kernel #63 (Global)', 'CLASSIC_DOUBLE_EN_41_0_4', 'headhunting-banner-images/Kernel 63 (Global).webp')])

    def test_a_path_outside_the_banner_art_fails(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected art path'):
            self.jobs([banner('Standard Pool #177 (Global)', 'DOUBLE_EN_41_0_9', '2026-10-09', '2026-10-23', image='/../asset-manifest.json')])

    def test_the_card_is_framed_whole_at_the_wiki_art_size(self):
        art = client_card_art(card_png())
        self.assertEqual(art.size, (1024, 559))
        # The card's opaque part (429x199) fills the width; the bands above and below are its
        # own colours blurred and darkened, not the transparent margin's black.
        self.assertEqual(art.getpixel((512, 280)), (200, 40, 40))
        band = art.getpixel((512, 5))
        self.assertTrue(band[0] > 40 and band[0] < 200, band)

    def test_cards_go_only_where_no_art_is(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = {'files': {'headhunting-banner-images/Standard Pool 176 (Global).webp': {'bytes': 1, 'sha256': 'x'}}}
            sources, asked, refs = {}, [], []
            jobs = [('Standard Pool #176 (Global)', 'DOUBLE_EN_41_0_8', 'headhunting-banner-images/Standard Pool 176 (Global).webp'),
                    ('Standard Pool #177 (Global)', 'DOUBLE_EN_41_0_9', 'headhunting-banner-images/Standard Pool 177 (Global).webp'),
                    ('Kernel #63 (Global)', 'CLASSIC_DOUBLE_EN_41_0_4', 'headhunting-banner-images/Kernel 63 (Global).webp')]
            fetch = lambda ref, pool: asked.append((ref, pool)) or (card_png() if pool.startswith('DOUBLE') else None)
            with patch('sync_recurring_banner_art.ROOT', root), contextlib.redirect_stdout(io.StringIO()) as out:
                changed = place_client_cards(jobs, manifest, sources, fetch=fetch, ref=lambda: refs.append(1) or 'c' * 40)
            # #176 has art already: its card is never fetched. One resolve serves the run.
            self.assertEqual(asked, [('c' * 40, 'DOUBLE_EN_41_0_9'), ('c' * 40, 'CLASSIC_DOUBLE_EN_41_0_4')])
            self.assertEqual(refs, [1])
            target = 'headhunting-banner-images/Standard Pool 177 (Global).webp'
            self.assertEqual(changed, [target])
            data = (root / target).read_bytes()
            self.assertEqual(manifest['files'][target], {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'width': 1024, 'height': 559})
            self.assertEqual(sources, {target: f"client-card:{'c' * 40}:assets/dyn/%5B%5Ben%5D%5D/arts/ui/homebanners/gacha/picdouble_en_41_0_9.png"})
            self.assertIn('Waiting for art: Kernel #63 (Global)', out.getvalue())
        # Nothing to place: no resolve at all.
        with patch('sync_recurring_banner_art.ROOT', root):
            self.assertEqual(place_client_cards(jobs[:1], manifest, {}, fetch=fetch, ref=lambda: self.fail('resolved')), [])

    def test_the_wiki_upload_replaces_a_card(self):
        target = 'headhunting-banner-images/Standard Pool 175 (Global).webp'
        info = {'batchcomplete': '', 'query': {'pages': {'1': {'title': 'File:EN Standard Pool 175 banner.png',
            'imageinfo': [{'url': 'https://arknights.wiki.gg/images/EN_Standard_Pool_175_banner.png', 'sha1': 'a' * 40}]}}}}
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as data:
            root = Path(temp)
            (root / 'asset-manifest.json').write_text(json.dumps({'files': {target: {'bytes': 4, 'sha256': 'card'}}}))
            (root / 'sources').mkdir()
            (root / 'sources/recurring-banner-art.json').write_text(json.dumps({target: 'client-card:' + 'c' * 40 + ':pic.png'}))
            (Path(data) / 'source/data').mkdir(parents=True)
            (Path(data) / 'source/data/headhunting_banners.json').write_text('[]')
            with patch('sync_recurring_banner_art.ROOT', root), patch('sync_recurring_banner_art.utc_today', return_value=dt.date(2026, 9, 12)), \
                    patch.dict(os.environ, {'ARKPEDIA_DATA_ROOT': data}), patch('sync_recurring_banner_art.fetch', side_effect=[PAGE, info]), \
                    patch('sync_recurring_banner_art.download', return_value=b'wiki') as download, patch('subprocess.run'), \
                    contextlib.redirect_stdout(io.StringIO()):
                sync_recurring_banner_art.main()
            download.assert_called_once_with('https://arknights.wiki.gg/images/EN_Standard_Pool_175_banner.png')
            self.assertEqual(json.loads((root / 'asset-manifest.json').read_text())['files'][target]['sha256'], hashlib.sha256(b'wiki').hexdigest())
            self.assertEqual(json.loads((root / 'sources/recurring-banner-art.json').read_text())[target], 'a' * 40)


if __name__ == '__main__':
    unittest.main()
