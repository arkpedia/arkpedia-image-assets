import contextlib
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import sync_recurring_banner_art
from sync_recurring_banner_art import image_info, read_sources, rows, wikitext
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
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = '{"files":{}}\n'
            (root / 'asset-manifest.json').write_text(manifest)
            out = io.StringIO()
            with patch('sync_recurring_banner_art.ROOT', root), patch('sync_recurring_banner_art.utc_today', return_value=today), \
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


class SourceTests(unittest.TestCase):
    TARGET = 'headhunting-banner-images/Standard Pool 175 (Global).webp'
    INFO = {'batchcomplete': '', 'query': {'pages': {'1': {'title': 'File:EN Standard Pool 175 banner.png',
        'imageinfo': [{'url': 'https://arknights.wiki.gg/images/EN_Standard_Pool_175_banner.png', 'sha1': 'a' * 40}]}}}}

    def test_only_wiki_uploads_may_be_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'recurring-banner-art.json'
            self.assertEqual(read_sources(path), {})
            path.write_text(json.dumps({self.TARGET: 'a' * 40}))
            self.assertEqual(read_sources(path), {self.TARGET: 'a' * 40})
            # The client-card stand-ins this script once made, and anything else that is not a wiki sha1.
            for other in ('client-card:' + 'c' * 40 + ':pic.png', 'A' * 40, ''):
                path.write_text(json.dumps({self.TARGET: other}))
                with self.assertRaisesRegex(ValueError, 'Only wiki uploads'):
                    read_sources(path)

    def test_the_wiki_upload_is_published_with_its_sha1(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'asset-manifest.json').write_text(json.dumps({'files': {}}))
            with patch('sync_recurring_banner_art.ROOT', root), patch('sync_recurring_banner_art.utc_today', return_value=dt.date(2026, 9, 12)), \
                    patch('sync_recurring_banner_art.fetch', side_effect=[PAGE, self.INFO]), \
                    patch('sync_recurring_banner_art.download', return_value=b'wiki') as download, patch('subprocess.run'), \
                    contextlib.redirect_stdout(io.StringIO()):
                sync_recurring_banner_art.main()
            download.assert_called_once_with('https://arknights.wiki.gg/images/EN_Standard_Pool_175_banner.png')
            self.assertEqual(json.loads((root / 'asset-manifest.json').read_text())['files'][self.TARGET]['sha256'], hashlib.sha256(b'wiki').hexdigest())
            self.assertEqual(json.loads((root / 'sources/recurring-banner-art.json').read_text()), {self.TARGET: 'a' * 40})

    def test_a_banner_without_a_wiki_upload_gets_no_art(self):
        missing = {'batchcomplete': '', 'query': {'pages': {'-1': {'title': 'File:EN Standard Pool 175 banner.png', 'missing': ''}}}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'asset-manifest.json').write_text(json.dumps({'files': {}}))
            with patch('sync_recurring_banner_art.ROOT', root), patch('sync_recurring_banner_art.utc_today', return_value=dt.date(2026, 9, 12)), \
                    patch('sync_recurring_banner_art.fetch', side_effect=[PAGE, missing]), \
                    patch('sync_recurring_banner_art.download') as download, contextlib.redirect_stdout(io.StringIO()) as out:
                sync_recurring_banner_art.main()
            download.assert_not_called()
            self.assertEqual(out.getvalue(), 'Recurring banner art is current.\n')
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['asset-manifest.json'])

    def test_official_upload_restores_only_an_approved_retired_path(self):
        for approved in (False, True):
            with self.subTest(approved=approved), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / 'asset-manifest.json').write_text(json.dumps({'files': {}}))
                entry = {'reason': 'Removed interim client-card artwork'}
                if approved:
                    entry['restoreFrom'] = 'recurring-wiki-upload'
                retired = {'schemaVersion': 1, 'paths': {self.TARGET: entry, 'unrelated.webp': {'reason': 'Unrelated retirement'}}}
                (root / 'retired-assets.json').write_text(json.dumps(retired))
                with patch('sync_recurring_banner_art.ROOT', root), patch('sync_recurring_banner_art.utc_today', return_value=dt.date(2026, 9, 12)), \
                        patch('sync_recurring_banner_art.fetch', side_effect=[PAGE, self.INFO]), \
                        patch('sync_recurring_banner_art.download', return_value=b'official-wiki') as download, patch('subprocess.run') as stage, \
                        contextlib.redirect_stdout(io.StringIO()):
                    if approved:
                        sync_recurring_banner_art.main()
                        self.assertEqual(json.loads((root / 'retired-assets.json').read_text())['paths'], {'unrelated.webp': {'reason': 'Unrelated retirement'}})
                        self.assertIn('retired-assets.json', stage.call_args.args[0])
                        self.assertTrue((root / self.TARGET).exists())
                    else:
                        with self.assertRaisesRegex(ValueError, 'retired without approval'):
                            sync_recurring_banner_art.main()
                        download.assert_not_called()
                        stage.assert_not_called()
                        self.assertEqual(json.loads((root / 'retired-assets.json').read_text()), retired)

    def test_missing_official_upload_keeps_approved_retirement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'asset-manifest.json').write_text(json.dumps({'files': {}}))
            retired = {'schemaVersion': 1, 'paths': {self.TARGET: {'reason': 'Removed interim art', 'restoreFrom': 'recurring-wiki-upload'}}}
            (root / 'retired-assets.json').write_text(json.dumps(retired))
            missing = {'query': {'pages': {'-1': {'missing': ''}}}}
            with patch('sync_recurring_banner_art.ROOT', root), patch('sync_recurring_banner_art.utc_today', return_value=dt.date(2026, 9, 12)), \
                    patch('sync_recurring_banner_art.fetch', side_effect=[PAGE, missing]), patch('sync_recurring_banner_art.download') as download, \
                    contextlib.redirect_stdout(io.StringIO()):
                sync_recurring_banner_art.main()
            download.assert_not_called()
            self.assertEqual(json.loads((root / 'retired-assets.json').read_text()), retired)


if __name__ == '__main__':
    unittest.main()
