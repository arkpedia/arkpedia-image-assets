> Migrated from `arkpedia/arkpedia` commit `5063510197bafb7990404b8727c31014ebb7d0cf`. The notes below describe capture provenance and processing. Import tools now live under `scripts/imports/` in the private app.

# Source art

The captures the site's masked assets were cut from, as webp, keeping their original
names. Written by `scripts/imports/import-mode-marks.py`, which takes the folder they arrive in:

```bash
python3 scripts/imports/import-mode-marks.py "~/Desktop/Arknights Stages Page"
```

**Only what shipping cannot give back.** This folder held 48 pictures once, and 35 of
them held nothing: they were byte-identical to the file they produced, or a raster of an
SVG that is in the repo as SVG, or a pure trim of transparent margin. A megabyte of
nothing. They are gone; `git log` has them if that turns out to be wrong.

What is left is the kind that cannot be recovered, and the reason generalises: their
importer **masks**. An opaque capture goes in — emblem plus its background — and an
emblem on alpha comes out, so the original colours and surround exist nowhere else.

| folder | what the site serves | produced by |
| --- | --- | --- |
| `story-marks/` (14) | `public/story-marks/` | `scripts/imports/import-story-marks.py` |
| `act-marks/` (4) | `public/act-marks/` | `scripts/imports/import-act-marks.py` |

`archivable()` in the importer decides what lands here: subfolders are kept, the top
level is not. This importer's own inputs are the recoverable kind, by the measurement
above; a subfolder belongs to an importer whose losses this script cannot see, and the
safe answer there is to keep. **So new hand-fed art goes in a subfolder if it is worth
keeping.** Screenshots are dropped by name wherever they sit.

The four act wordmarks are the one known exception — they are byte-identical to what
shipped, so they are 16 kB of redundancy the subfolder rule keeps. That is cheaper than
a per-file pixel comparison, which is the alternative and is fragile.

**Why any of this exists.** None of it is fetchable. These emblems are UI art that no
asset mirror this project can reach carries — not yuanyan3060/ArknightsGameResource (it
has no `ui/`), nor fexli/ArknightsResource, Aceship/Arknight-Images, arknights.wiki.gg
or prts.wiki. They were traced or captured from the live game by hand, and re-deriving
one means capturing it again.

**Archival use.** These captures are publicly preserved here for reproducible imports. The website uses the processed files in the repository root; it does not load these captures.

**Formats.** Flat art is archived lossless; captures at quality 88, chosen by how many
colours are in the file.
