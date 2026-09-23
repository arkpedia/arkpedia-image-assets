#!/usr/bin/env python3
"""Publish current Standard and Kernel banner art from the EN wiki uploads.

Recurring banners are not present in the public resource mirror used by
sync_images.py. Their structured yearly wiki rows name the banner number and
window; the corresponding EN upload is the display asset used by the site.
"""
import datetime
import hashlib
import io
import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
API = 'https://arknights.wiki.gg/api.php'
UA = 'Arkpedia-assets/1.0 (+https://arkpedia.net)'
SSL = __import__('ssl').create_default_context(cafile=certifi.where())
SOON = datetime.timedelta(days=7)
RECENT = datetime.timedelta(days=45)


def fetch(params):
    url = f'{API}?{urllib.parse.urlencode(params)}'
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), context=SSL, timeout=120) as response:
        return json.load(response)


def utc_today():
    return datetime.datetime.now(datetime.timezone.utc).date()


def wikitext(today):
    """Return the banner page wikitext for today's year, or '' in January until it exists.

    The API answers a missing page with HTTP 200 and error code missingtitle.
    The wiki creates a year's page around New Year, as late as January 21 so
    far, so during January (UTC) a missing page means the year has no rows yet,
    as in the app's sync-recurring-banners.mjs. From February 1 a missing page
    means it was moved, renamed or never made, and an empty green run would
    hide that for the rest of the year, so it fails like any other error.
    """
    page = f'Headhunting/Banners/{today.year}'
    data = fetch({'action': 'parse', 'page': page, 'prop': 'wikitext', 'format': 'json'})
    error = data.get('error')
    if error and error.get('code') == 'missingtitle':
        if today.month == 1:
            return ''
        raise ValueError(f'{page} does not exist, and only in January may a new year\'s page be missing: {error}')
    if error:
        raise ValueError(f'{page}: {error}')
    return data['parse']['wikitext']['*']


def rows(text):
    for block in re.findall(r'\{\{Banners cell\s*([\s\S]*?)\}\}', text):
        fields = dict(re.findall(r'^\s*\|\s*([^=]+?)\s*=\s*(.*?)\s*$', block, re.M))
        kind = fields.get('type', '').strip()
        number = fields.get('no', '').strip()
        if kind not in {'standard', 'kernel'} or not number.isdigit():
            continue
        try:
            start = datetime.datetime.strptime(fields['start'].split()[0], '%Y/%m/%d').date()
            end = datetime.datetime.strptime(fields['end'].split()[0], '%Y/%m/%d').date()
        except (KeyError, ValueError):
            continue
        yield kind, number, start, end


def image_info(title):
    data = fetch({'action': 'query', 'prop': 'imageinfo', 'iiprop': 'url|sha1', 'format': 'json', 'titles': title})
    page = next(iter(data['query']['pages'].values()))
    return None if 'missing' in page or not page.get('imageinfo') else page['imageinfo'][0]


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(request, context=SSL, timeout=120) as response:
        image = Image.open(io.BytesIO(response.read())).convert('RGB')
    if image.width > 1024:
        image = image.resize((1024, round(image.height * 1024 / image.width)), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, 'WEBP', quality=85)
    return out.getvalue()


def main():
    today = utc_today()
    text = wikitext(today)
    sources_path = ROOT / 'sources' / 'recurring-banner-art.json'
    sources = json.loads(sources_path.read_text()) if sources_path.exists() else {}
    manifest_path = ROOT / 'asset-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    changed = []

    for kind, number, start, end in rows(text):
        if start > today + SOON or end < today - RECENT:
            continue
        prefix = 'Standard Pool' if kind == 'standard' else 'Kernel'
        target = f'headhunting-banner-images/{prefix} {number} (Global).webp'
        title = f'File:EN {prefix} {number} banner.png'
        info = image_info(title)
        if not info or target in manifest['files'] and sources.get(target) == info['sha1']:
            continue
        data = download(info['url'])
        (ROOT / target).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / target).write_bytes(data)
        manifest['files'][target] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        sources[target] = info['sha1']
        changed.append(target)

    if changed:
        manifest['files'] = dict(sorted(manifest['files'].items()))
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n')
        sources_path.parent.mkdir(parents=True, exist_ok=True)
        sources_path.write_text(json.dumps(dict(sorted(sources.items())), indent=2) + '\n')
        subprocess.run(['git', 'add', '--sparse', '--', 'asset-manifest.json', 'sources/recurring-banner-art.json', *changed], cwd=ROOT, check=True)
        print('\n'.join(f'  + {path}' for path in changed))
    else:
        print('Recurring banner art is current.')


if __name__ == '__main__':
    main()
