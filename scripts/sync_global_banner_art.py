#!/usr/bin/env python3
"""Refresh Global event/featured key art from EN uploads, using Arkpedia's schedule.

The website only reads the resulting, revision-pinned Arkpedia assets. The wiki
is an image import source, not the authority for gameplay values or release times.
Missing EN art is retried daily; HTTP failures fail the job rather than looking
like a successful refresh. No CN upload is ever substituted for an EN match.
"""
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.parse
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
API = 'https://arknights.wiki.gg/api.php'
UA = 'Arkpedia-assets/1.0 (+https://arkpedia.net)'


def fetch(url):
    return subprocess.check_output(['curl', '--fail', '--silent', '--show-error', '--location',
        '--retry', '3', '--max-time', '90', '--user-agent', UA, url])


def wiki_titles(name):
    base = re.sub(r'^\[[^\]]*\]\s*', '', name).replace('#', '').replace(' (Global)', '').strip()
    candidates = [base]
    for before, after in [('1st Half', 'Part 1'), ('2nd Half', 'Part 2'), ('Part One', 'Part 1'), ('Part Two', 'Part 2')]:
        if before in base:
            candidates.append(base.replace(before, after))
    candidates.extend([re.sub(r'\s+(?:1st|2nd)\s+Half$', '', base), re.sub(r'\s+Rerun$', '', base)])
    # MediaWiki file titles are case-sensitive after the first letter. Our
    # schedule sometimes capitalises "The" where the EN upload uses "the".
    candidates += [re.sub(r'\b(?:The|Of|And|A|An|In|To|For)\b', lambda m: m[0].lower() if m.start() else m[0], c) for c in candidates]
    return list(dict.fromkeys(f'File:EN {c} banner.png' for c in candidates if c))


def image_info(titles):
    query = urllib.parse.urlencode({'action': 'query', 'prop': 'imageinfo', 'iiprop': 'url|sha1',
        'format': 'json', 'titles': '|'.join(titles)})
    data = json.loads(fetch(f'{API}?{query}'))
    if 'error' in data:
        raise ValueError(data['error'])
    query = data['query']
    found = {page['title']: page['imageinfo'][0] for page in query['pages'].values() if page.get('imageinfo')}
    normalized = {row['from']: row['to'] for row in query.get('normalized', [])}
    return next(((title, found[normalized.get(title, title)]) for title in titles if normalized.get(title, title) in found), None)


def window(text):
    dates = re.findall(r'\d{4}/\d{1,2}/\d{1,2}', text or '')
    return tuple(dt.datetime.strptime(value, '%Y/%m/%d').date() for value in dates) if len(dates) == 2 else None


def jobs(data_root, today):
    data = data_root / 'source/data'
    records = [(b['name'], b.get('global_date'), b.get('banner_image'))
        for b in json.loads((data / 'headhunting_banners.json').read_text())
        if b.get('pull_type') not in {'standard', 'kernel'}]
    for file in sorted((data / 'events').glob('events_*.json')):
        records.extend((e['name'], (e.get('global') or {}).get('dateRange'), e.get('poster')) for e in json.loads(file.read_text()))
    seen = set()
    for name, dates, target in records:
        dates = window(dates)
        if not dates or not target or dates[0] > today + dt.timedelta(days=7) or dates[1] < today - dt.timedelta(days=45):
            continue
        target = target.lstrip('/')
        if not target.startswith(('event-poster/', 'headhunting-banner-images/')) or '..' in Path(target).parts:
            raise ValueError(f'Unexpected art path: {target}')
        if target not in seen:
            seen.add(target)
            yield name, target


def main():
    data_root = Path(os.environ['ARKPEDIA_DATA_ROOT'])
    sources_path = ROOT / 'sources/global-banner-art.json'
    sources = json.loads(sources_path.read_text()) if sources_path.exists() else {}
    manifest_path = ROOT / 'asset-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    changed, waiting = [], []
    for name, target in jobs(data_root, dt.date.today()):
        hit = image_info(wiki_titles(name))
        if not hit:
            waiting.append(name)
            continue
        title, info = hit
        if sources.get(target, {}).get('sha1') == info['sha1'] and target in manifest['files']:
            continue
        with Image.open(io.BytesIO(fetch(info['url']))) as source:
            source.load()
            if not 0 < source.width <= 16384 or not 0 < source.height <= 16384:
                raise ValueError(f'Invalid image dimensions for {name}')
            image = source.convert('RGB')
            if image.width > 1024:
                image = image.resize((1024, round(image.height * 1024 / image.width)), Image.Resampling.LANCZOS)
            encoded = io.BytesIO()
            image.save(encoded, 'WEBP', quality=85)
            content = encoded.getvalue()
        path = ROOT / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        manifest['files'][target] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(), 'width': image.width, 'height': image.height}
        sources[target] = {'title': title, 'url': info['url'], 'sha1': info['sha1']}
        changed.append(target)
        print(f'Updated: {name}')
    if changed:
        sources_path.parent.mkdir(parents=True, exist_ok=True)
        sources_path.write_text(json.dumps(dict(sorted(sources.items())), ensure_ascii=False, indent=2) + '\n')
        manifest['files'] = dict(sorted(manifest['files'].items()))
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n')
        subprocess.run(['git', 'add', '--sparse', '--', 'asset-manifest.json', str(sources_path.relative_to(ROOT)), *changed], cwd=ROOT, check=True)
    report = f'Updated {len(changed)} Global event/banner images; {len(waiting)} EN uploads still unavailable.'
    print(report)
    for name in waiting:
        print(f'Awaiting EN upload (retried next run): {name}')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write(report + '\n' + ''.join(f'- Awaiting EN upload: {name}\n' for name in waiting))


if __name__ == '__main__':
    main()
