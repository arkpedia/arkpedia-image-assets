#!/usr/bin/env python3
"""Reassemble the preserved full-resolution Terra map without resizing."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='New PNG path outside the asset repository')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    output = args.output.resolve()
    if output == root or root in output.parents:
        parser.error('Choose an output outside the repository: the assembled map exceeds its file-size limit.')
    if output.suffix.lower() != '.png':
        parser.error('The output must have a .png extension.')
    if output.exists():
        parser.error(f'Refusing to overwrite {output}')
    provenance = json.loads((root / 'sources/anniversary-5-terra.json').read_text())
    records = json.loads((root / 'asset-manifest.json').read_text())['files']
    source = next(row for row in provenance['assets'] if row['sourcePath'] == 'full_map.png')
    canvas = Image.new(source['mode'], (source['width'], source['height']))
    for tile in source['tiles']:
        path = root / tile['path']
        with path.open('rb') as stream:
            sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
        if sha256 != records[tile['path']]['sha256']:
            raise ValueError(f'Tile hash mismatch: {path}')
        with Image.open(path) as image:
            image.load()
            if image.mode != source['mode'] or image.size != (tile['width'], tile['height']):
                raise ValueError(f'Tile dimensions/mode mismatch: {path}')
            canvas.paste(image, (tile['x'], tile['y']))
    with output.open('xb') as stream:
        canvas.save(stream, format='PNG')
    print(f'Saved {canvas.width} × {canvas.height} {canvas.mode} map to {output}')


if __name__ == '__main__':
    main()
