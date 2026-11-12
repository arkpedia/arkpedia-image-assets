"""Match Global key art to the same official notice that confirms its dates."""
import datetime as dt
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse, unquote


def data_path(root):
    source = root / 'source/data'
    return source if source.is_dir() else root / 'data'


def artwork_path(value):
    if not isinstance(value, str):
        return None
    if value.startswith('https://raw.githubusercontent.com/arkpedia/arkpedia-image-assets/'):
        parts = urlparse(value).path.split('/', 4)
        if len(parts) != 5 or not re.fullmatch(r'[a-f0-9]{40}', parts[3]):
            return None
        value = unquote(parts[4])
    value = value.lstrip('/')
    return value if value.startswith(('event-poster/', 'headhunting-banner-images/')) and '..' not in Path(value).parts else None


def folded(value):
    value = re.sub(r'^\[[^\]]*\]\s*', '', value)
    return ''.join(c for c in unicodedata.normalize('NFKD', value).lower() if c.isalnum())


def announcement_images(root, today):
    data = data_path(root)
    records = [(b.get('name', ''), b.get('banner_image'), (b.get('global_window') or {}).get('timingSource'), 'banner')
        for b in json.loads((data / 'headhunting_banners.json').read_text()) if not b.get('global_date_estimated')]
    for file in sorted((data / 'events').glob('events_*.json')):
        records.extend((e.get('name', ''), e.get('poster'), (e.get('global') or {}).get('timingSource'), 'event')
            for e in json.loads(file.read_text()) if not re.search(r'estimat|predict', (e.get('global') or {}).get('note') or '', re.I))
    found = {}
    for name, target, source, kind in records:
        match = re.fullmatch(r'https://(?:www\.)?arknights\.global/news/(\d+)/?', source or '')
        target = artwork_path(target)
        if not match or not target or not folded(name):
            continue
        file = data / 'official-news/global' / (match[1] + '.json')
        if not file.exists():
            continue
        post = json.loads(file.read_text())
        if (post.get('url') or '').rstrip('/') != source.rstrip('/'):
            continue
        published = post.get('publishTime')
        if not isinstance(published, (int, float)):
            continue
        day = dt.datetime.fromtimestamp(published / 1000, dt.timezone.utc).date()
        if not today - dt.timedelta(days=45) <= day <= today + dt.timedelta(days=1):
            continue
        lines = post.get('lines') or []
        candidates = []
        for art in post.get('art') or []:
            line = art.get('line')
            if not isinstance(line, int) or not 0 <= line < len(lines):
                continue
            heading = lines[line]
            if not re.match(r'^\d{2}\s', heading) or folded(name) not in folded(heading):
                continue
            if kind == 'event' and line != 0 or kind == 'banner' and not re.search(r'HEADHUNTING', heading, re.I):
                continue
            url = art.get('url') or ''
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.hostname != 'webusstatic.yo-star.com' or parsed.username or parsed.password \
                    or not parsed.path.startswith('/web-cms-test/upload/content/'):
                continue
            candidates.append({'url': url, 'sourcePage': source, 'title': post['title']})
        if len(candidates) == 1:
            found[target] = candidates[0]
    return found
