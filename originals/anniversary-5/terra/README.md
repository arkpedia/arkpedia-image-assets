# Fifth-anniversary Terra website assets

Imported on 2026-11-07 from the user-supplied folder `arknights 5th anni website`.
The reported source is the [Arknights fifth-anniversary Terra website](https://5thanniversary.arknights.global/terra).
That attribution has not been verified against individual live asset URLs; the
download's original source URLs and retrieval date were not supplied.

This archive is for future Arkpedia features. Files retain their original pixels,
resolution and transparency. It does not add a page or change the site's asset
configuration. Create appropriately sized delivery variants when a feature needs
them; these archival maps are too large for normal page loads.

| Folder | Contents |
| --- | --- |
| `character-avatars/` | 315 character avatars; source filenames retained. |
| `character-illustrations/` | 623 character illustrations, including 308 `_active` variants; source filenames retained. |
| `map-tiles/` | 68 named region/map pieces from the source `tiles/` folder. |
| `maps/` | The two smaller assembled maps, `full-map-r1.png` (11515 × 7919) and `full-map-r2.png` (5758 × 3960). |
| `maps/full-resolution/` | The largest assembled map (23029 × 15838), preserved as 24 lossless PNG tiles with their pixel coordinates in the filenames. |
| `backgrounds/` | Three background images. |
| `page-elements/` | Three decorative elements and `front-page.png`. |
| `logos/` | Two logos. |

All 1,018 source images are represented. The 1,015 images in the supplied ZIP
were verified byte-for-byte against the extracted folder; the duplicate ZIP and
`.DS_Store` metadata are omitted. The three assembled maps were outside the ZIP
and are also included.

1,017 source images are byte-identical copies. The largest map's original PNG
is 198,801,457 bytes, exceeding the repository's 100 MiB image limit. Its RGBA
pixels are preserved in 4096 × 4096 tiles (smaller at the edges), with each saved
tile decoded and compared to the source region. There is no resizing or lossy
compression. PNG metadata and the original encoded byte stream are not retained
for this one image; the original download remains available locally.

[Import provenance](../../../sources/anniversary-5-terra.json) records every
original filename, byte size, SHA-256, dimensions, destination and tile position.
`asset-manifest.json` at the repository root lists all 1,041 stored images.

## Reassemble the largest map

Install Pillow if necessary, then pass an output path outside this repository:

```sh
python3 originals/anniversary-5/terra/assemble_full_map.py /tmp/terra-full-map.png
```

Reassembly requires several gigabytes of available memory. It restores the exact
RGBA pixels and dimensions, but produces a newly encoded PNG whose file hash can
differ from the original. The script verifies the stored tiles against the asset
manifest before assembling them and refuses to overwrite an existing file.

These assets remain the property of their respective rights holders; see the
repository's existing rights notice.
