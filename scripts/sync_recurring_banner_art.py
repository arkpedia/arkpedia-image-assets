#!/usr/bin/env python3
"""Publish current Standard and Kernel banner art from the EN wiki uploads.

Recurring banners are not present in the public resource mirror used by
sync_images.py. Their structured yearly wiki rows name the banner number and
window; the corresponding EN upload is the display asset used by the site.

The wiki uploads a banner's art around the day it opens, but the Global client
ships the pool about two weeks before. Until the upload, a Standard banner the
app has recorded (arkpedia-data's headhunting_banners.json, which names the
pool and the art's path) gets interim art from the client: its home screen
card, arts/ui/homebanners/gacha/pic<pool>.png in ArknightsAssets2 (branch en),
framed to the wiki art's 1024x559 (client_card_art). The wiki's upload replaces
it once it exists, as it replaces any older upload. The client has no such card
for Kernel pools, so those wait for the wiki as before.
"""
import datetime
import hashlib
import io
import json
import math
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
API = 'https://arknights.wiki.gg/api.php'
UA = 'Arkpedia-assets/1.0 (+https://arkpedia.net)'
SSL = __import__('ssl').create_default_context(cafile=certifi.where())
SOON = datetime.timedelta(days=7)
RECENT = datetime.timedelta(days=45)
# A pool's card ships with the pool, about two weeks before it opens.
CARD_SOON = datetime.timedelta(days=21)
CARD_REPOSITORY = 'ArknightsAssets/ArknightsAssets2'
CARD_PATH = 'assets/dyn/%5B%5Ben%5D%5D/arts/ui/homebanners/gacha/pic{pool}.png'
# The wiki's EN banner art, as this script and the app's frame size it.
ART_SIZE = (1024, 559)


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
    means it was deleted or never made, and an empty green run would hide that
    for the rest of the year, so it fails like any other error.

    Moving a page leaves a redirect at the old title, not missingtitle; the
    wiki moved Headhunting/Banners/Former-2020..2024 this way. `redirects`
    makes the API parse the target page. It follows one redirect only, so a
    double redirect would still return '#REDIRECT [[...]]', which has no
    rows and would read as current; that fails in any month.
    """
    page = f'Headhunting/Banners/{today.year}'
    data = fetch({'action': 'parse', 'page': page, 'prop': 'wikitext', 'redirects': 1, 'format': 'json'})
    error = data.get('error')
    if error and error.get('code') == 'missingtitle':
        if today.month == 1:
            return ''
        raise ValueError(f'{page} does not exist, and only in January may a new year\'s page be missing: {error}')
    if error:
        raise ValueError(f'{page}: {error}')
    text = data['parse']['wikitext']['*']
    if text.lstrip().lower().startswith('#redirect'):
        raise ValueError(f'{page} is a redirect the API did not follow (a double redirect): {text.strip()[:120]!r}')
    return text


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
    # imageinfo resolves a moved file by itself; `redirects` keeps this read consistent with wikitext().
    data = fetch({'action': 'query', 'prop': 'imageinfo', 'iiprop': 'url|sha1', 'redirects': 1, 'format': 'json', 'titles': title})
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


def iso_day(value):
    return datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).date() if value else None


def card_jobs(data_root, today):
    """(name, pool id, art path) of each recorded Standard or Kernel banner running
    now, ended within RECENT, or opening within CARD_SOON."""
    for banner in json.loads((data_root / 'source/data/headhunting_banners.json').read_text()):
        window = banner.get('global_window') or {}
        start, end = iso_day(window.get('startAt')), iso_day(window.get('endAt'))
        if banner.get('pull_type') not in {'standard', 'kernel'} or not banner.get('globalPoolId') or not banner.get('banner_image'):
            continue
        if not start or not end or start > today + CARD_SOON or end < today - RECENT:
            continue
        target = banner['banner_image'].lstrip('/')
        if not target.startswith('headhunting-banner-images/') or '..' in Path(target).parts:
            raise ValueError(f'Unexpected art path for {banner["name"]}: {target}')
        yield banner['name'], banner['globalPoolId'], target


def client_card_art(data):
    """The card as banner art: cropped to its opaque part (it has a soft shadow), fitted
    whole into ART_SIZE, over itself enlarged to fill, blurred and darkened -- never
    stretched, and never cropped into its text."""
    with Image.open(io.BytesIO(data)) as source:
        source.load()
        if not 0 < source.width <= 4096 or not 0 < source.height <= 4096:
            raise ValueError(f'Invalid card dimensions {source.size}')
        card = source.convert('RGBA')
    opaque = card.getchannel('A').point(lambda value: 255 if value >= 250 else 0).getbbox()
    if not opaque:
        raise ValueError('The card has no opaque part')
    card = card.crop(opaque).convert('RGB')
    width, height = ART_SIZE
    cover = max(width / card.width, height / card.height)
    fill = card.resize((math.ceil(card.width * cover), math.ceil(card.height * cover)), Image.Resampling.LANCZOS)
    left, top = (fill.width - width) // 2, (fill.height - height) // 2
    fill = fill.crop((left, top, left + width, top + height)).filter(ImageFilter.GaussianBlur(24))
    art = ImageEnhance.Brightness(fill).enhance(0.45)
    fit = min(width / card.width, height / card.height)
    front = card.resize((round(card.width * fit), round(card.height * fit)), Image.Resampling.LANCZOS)
    art.paste(front, ((width - front.width) // 2, (height - front.height) // 2))
    return art


def card_ref():
    """The art mirror's en branch head, from git itself: no API token, no rate limit."""
    out = subprocess.run(['git', 'ls-remote', '--exit-code', f'https://github.com/{CARD_REPOSITORY}.git', 'refs/heads/en'],
        capture_output=True, text=True, timeout=60, check=True, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'}).stdout
    commit = out.split()[0] if out.split() else ''
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError(f'Cannot resolve {CARD_REPOSITORY} en: {out!r}')
    return commit


def fetch_card(ref, pool):
    """The card's bytes, or None when the client has none for the pool (404)."""
    url = f'https://raw.githubusercontent.com/{CARD_REPOSITORY}/{ref}/{CARD_PATH.format(pool=pool.lower())}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), context=SSL, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def place_client_cards(jobs, manifest, sources, fetch=fetch_card, ref=card_ref):
    """Write interim art for each job whose path has no art yet; return the paths written.
    Art already there -- the wiki's, or a card placed before -- is left alone."""
    changed, commit = [], None
    for name, pool, target in jobs:
        if target in manifest['files']:
            continue
        commit = commit or ref()
        data = fetch(commit, pool)
        if data is None:
            print(f'Waiting for art: {name} (the client has no card for {pool})')
            continue
        encoded = io.BytesIO()
        art = client_card_art(data)
        art.save(encoded, 'WEBP', quality=85)
        content = encoded.getvalue()
        (ROOT / target).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / target).write_bytes(content)
        manifest['files'][target] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(), 'width': art.width, 'height': art.height}
        # Not a wiki sha1, so the wiki's upload replaces it (main's wiki loop).
        sources[target] = f'client-card:{commit}:{CARD_PATH.format(pool=pool.lower())}'
        changed.append(target)
        print(f'Interim art from the client card: {name}')
    return changed


def main():
    today = utc_today()
    data_root = Path(os.environ['ARKPEDIA_DATA_ROOT'])
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

    changed += place_client_cards(card_jobs(data_root, today), manifest, sources)

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
