import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
import sync_recurring_banner_art
from sync_recurring_banner_art import rows, wikitext
from unittest.mock import patch

# The API's answer (HTTP 200) for Headhunting/Banners/2027 on 2026-09-23, before the page existed.
MISSING = json.loads('{"error":{"code":"missingtitle","info":"The page you specified doesn\'t exist.","*":"See https://arknights.wiki.gg/api.php for API usage. Subscribe to the mediawiki-api-announce mailing list at &lt;https://lists.wikimedia.org/postorius/lists/mediawiki-api-announce.lists.wikimedia.org/&gt; for notice of API deprecations and breaking changes."}}')
PAGE = {'parse': {'title': 'Headhunting/Banners/2026', 'wikitext': {'*': '{{Banners cell\n|type = standard\n|no = 175\n'
    '|start = 2026/09/11 04:00:00\n|end = 2026/09/25 03:59:59\n|operators = A, B, C, D, E}}'}}}

class YearlyPageTests(unittest.TestCase):
    def test_missing_yearly_page_has_no_rows(self):
        with patch('sync_recurring_banner_art.fetch', return_value=MISSING) as fetch:
            self.assertEqual(list(rows(wikitext(2027))), [])
        self.assertEqual(fetch.call_args.args[0]['page'], 'Headhunting/Banners/2027')

    def test_other_api_errors_still_fail(self):
        for error in ({'code': 'ratelimited', 'info': "You've exceeded your rate limit."}, {'code': 'invalidtitle', 'info': 'Bad title.'}):
            with patch('sync_recurring_banner_art.fetch', return_value={'error': error}), self.assertRaisesRegex(ValueError, error['code']):
                wikitext(2026)

    def test_existing_page_yields_its_rows(self):
        with patch('sync_recurring_banner_art.fetch', return_value=PAGE):
            self.assertEqual(list(rows(wikitext(2026))), [('standard', '175', dt.date(2026, 9, 11), dt.date(2026, 9, 25))])

    def test_run_before_the_page_exists_is_current(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = '{"files":{}}\n'
            (root / 'asset-manifest.json').write_text(manifest)
            out = io.StringIO()
            with patch('sync_recurring_banner_art.ROOT', root), patch('sync_recurring_banner_art.fetch', return_value=MISSING) as fetch, contextlib.redirect_stdout(out):
                sync_recurring_banner_art.main()
            # One call: no image lookups, no downloads, nothing written or staged.
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(out.getvalue(), 'Recurring banner art is current.\n')
            self.assertEqual((root / 'asset-manifest.json').read_text(), manifest)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['asset-manifest.json'])

if __name__ == '__main__':
    unittest.main()
