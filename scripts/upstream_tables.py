#!/usr/bin/env python3
"""Fetch the game tables the operators job joins art through, at the commits the release read.

    python scripts/upstream_tables.py <arkpedia-data>/source/data/upstream.lock.json <out dir>

The content release pins every game-data mirror it reads to one commit per run and publishes
the pins with its records, in arkpedia-data's source/data/upstream.lock.json (arkpedia's
scripts/content/pin-upstream.mjs and cn-tables.mjs). This job reads those records to discover
new operators and enemies, so it joins them to art through the same tables. Until 2026-09 it
curled PuppiizSunniiz/ArknightsGameData_YoStar at main and Kengxxiao at master instead: a
different English mirror than the release's, whose last EN data was 09-11 while the release
already read the 09-23 patch, at whatever commit each branch had reached (OR-11).

- English: ArknightsAssets/ArknightsGamedata at its locked commit,
  en/gamedata/excel/<table>.json -- the checkout the release's stages read.
- Chinese: the lock's cnTables, the one mirror and commit the release's upstream-cn stage
  settled on, <folder>/excel/<table>.json; for a lock from before cnTables, Kengxxiao at its
  locked commit, zh_CN/gamedata.

A table without a locked commit has no address: the job fails rather than read a branch.

The art itself still comes from yuanyan3060/ArknightsGameResource at its branch head
(sync_images.py). This sync runs hours before the release, which pins whatever commit this
repository has reached by then, and every file is checked against the git blob id the mirror's
tree names, so a moving head cannot hand the sync other bytes than it records.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

TABLES = ('building_data', 'character_table', 'skill_table')
EN_REPOSITORY = 'ArknightsAssets/ArknightsGamedata'
EN_FOLDER = 'en/gamedata'
# The CN table sources arkpedia's cn-tables.mjs may settle on, with the folder that holds
# excel/ in each (CN_TABLE_SOURCES in pin-upstream.mjs).
CN_SOURCES = {
    'Kengxxiao/ArknightsGameData': 'zh_CN/gamedata',
    'yuanyan3060/ArknightsGameResource': 'gamedata',
}
CN_FALLBACK = 'Kengxxiao/ArknightsGameData'
SHA = re.compile(r'^[0-9a-f]{40}$')


def read_lock(path):
    lock = json.loads(Path(path).read_text())
    if not isinstance(lock, dict) or lock.get('version') != 1 or not isinstance(lock.get('repositories'), dict):
        raise ValueError(f'{path} is not a version 1 upstream lock')
    return lock


def locked_commit(lock, repository):
    commit = (lock['repositories'].get(repository) or {}).get('commit')
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        raise ValueError(f'The upstream lock pins no commit for {repository}; refusing to read its branch')
    return commit


def sources(lock):
    """{'en': (repository, commit, folder), 'cn': (...)} as the release read them."""
    cn = lock.get('cnTables')
    if cn is not None:
        repository, commit, folder = cn.get('repository'), cn.get('commit'), cn.get('folder')
        if repository not in CN_SOURCES or folder != CN_SOURCES[repository] or not isinstance(commit, str) or not SHA.fullmatch(commit):
            raise ValueError(f'The upstream lock\'s cnTables names no known CN table source at a commit: {json.dumps(cn)}')
        cn_source = (repository, commit, folder)
    else:
        cn_source = (CN_FALLBACK, locked_commit(lock, CN_FALLBACK), CN_SOURCES[CN_FALLBACK])
    return {'en': (EN_REPOSITORY, locked_commit(lock, EN_REPOSITORY), EN_FOLDER), 'cn': cn_source}


def output_name(region, table):
    """The file names the sync step's environment points at."""
    return f'building-{region}.json' if table == 'building_data' else f'{table}-{region}.json'


def table_urls(lock):
    """{output file name: raw URL at the locked commit} for every table the sync joins through."""
    urls = {}
    for region, (repository, commit, folder) in sources(lock).items():
        for table in TABLES:
            urls[output_name(region, table)] = f'https://raw.githubusercontent.com/{repository}/{commit}/{folder}/excel/{table}.json'
    return urls


def main(argv):
    if len(argv) != 2:
        raise SystemExit('usage: upstream_tables.py <upstream.lock.json> <out dir>')
    lock_path, out = argv
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, url in table_urls(read_lock(lock_path)).items():
        print(f'{name} <- {url}', flush=True)
        subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location', '--retry', '3', '--max-time', '300',
                        url, '--output', str(out_dir / name)], check=True)


if __name__ == '__main__':
    main(sys.argv[1:])
