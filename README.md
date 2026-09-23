# Arkpedia image assets

Icons, banner art, event art, and other image media used by [Arkpedia](https://github.com/Arkpedia/arkpedia).

## Repository map

| Location | Contents |
| --- | --- |
| `essential-icons/`, `class-icons/`, `branch-icons/`, `faction-icons/`, `stat-icons/` | Operator and interface symbols. |
| `*-star-icons/`, `skill-icons/`, `base-skill-icons/` | Operator portraits and skill icons. |
| `headhunting-banner-images/`, `event-poster/`, `content-art/`, `album-covers/`, `cg-collection/` | Banners, event art, music covers, and scenes. |
| `stages-images/`, `ra-map/`, `enemies-icons/`, `enemy-stat-icons/` | Stage maps and enemy artwork. |
| `*-marks/`, `alliance-icons/`, `stronghold-*/`, `item-icons/`, `material-icons/` | Mode emblems, game-mode UI, and material icons. |
| `originals/` | Preserved original image files. |
| `originals/source-art/` | Manual captures retained so masked/processed emblems can be reproduced. See its provenance notes. |
| `sources/` and `source.json` | Per-import provenance and the initial repository import source. |
| `asset-manifest.json` | File sizes and SHA-256 digests. |

Root delivery folders retain their existing names because deployed applications use those URLs. Put archival material in `originals/`; do not rename delivered files for tidiness.

## Updating an image

1. Add the delivery file to its existing category; prefer WebP for compact delivery and retain a useful original under `originals/`.
2. Record its actual upstream source or manual-capture provenance. Do not replace unknown provenance with a guess.
3. Update `asset-manifest.json` with its size and SHA-256 digest.
4. In the private application, update `data/assets/external-asset-index.json` and run `npm run check:assets`. Publish the asset before the application references it.

Operator artwork and responsive variants belong in [arkpedia-skin-assets](https://github.com/arkpedia/arkpedia-skin-assets); voice recordings belong in the language-specific voice repositories; palette corrections belong in [arkpedia-color-palette](https://github.com/arkpedia/arkpedia-color-palette).

These game assets remain the property of Hypergryph, Yostar, and their respective rights holders. This repository does not grant a license to reuse or redistribute them. Corrections and takedown requests may be submitted through the repository issue tracker.

## Updates and validation

A daily public Actions run at 16:11 UTC checks **5,002 explicitly mapped operator avatars, skill/base-skill icons, material icons and enemy icons** against `yuanyan3060/ArknightsGameResource`. `asset-source-map.json` records exact upstream paths and blob hashes; accepted existing images form the initial baseline and are only re-encoded when their upstream blob changes. Operator base-skill discovery reads EN then CN building tables, while combat skills join character-table skill IDs to skill-table icon IDs so shared generic icons do not depend on filename guesses. Use `scripts/build_source_map.py` with public EN game-data/resource snapshots to extend exact mappings, then review the diff; add manually verified paths for other categories. Operator discovery maps a new operator's portraits, skill icons and token by character ID, and enemy discovery maps each `arkpedia-data` enemy record's own `icon` path to `enemy/<id>.png`. Both skip any file `asset-manifest.json` already lists: hand-added art is never re-fetched or re-encoded, and joins the map only by review with its current upstream blob recorded (`build_source_map.py` for skill, base-skill and material icons; a manual map row for portraits). Unmapped banners, maps, UI assets and manual captures are preserved; this job does not pretend to discover their sources automatically.

Syncs never delete media. Missing upstream paths and bulk replacements stop the job for review. A source-map expansion can also refresh already mapped files when it discovers a newer upstream blob; treat those binary changes as part of the PR scope and verify the image count and dimensions before merging. The validator checks the complete manifest inventory, decodes images, verifies dimensions and SHA-256, and rejects empty or oversized files. PR/manual validation checks all bytes and runs the scripts' unit tests; daily sync validation checks changed bytes. Standard public runners are free; jobs have timeouts, no uploaded artifacts, and weekly grouped Actions dependency updates. `source.json` retains the historical migration provenance; ongoing updates use the public mirror in `asset-source-map.json`, never the private application.

Global event and featured-banner art is refreshed daily from explicitly English uploads. The importer reads release windows and image paths from `arkpedia-data`, records image provenance in `sources/global-banner-art.json`, retries missing English uploads, and validates every changed image against the asset manifest. Recurring Standard/Kernel banners have their own discovery step. Consumers use pinned files in this repository, never the upstream image host.

The run has one job per source, in this order: Global key art, recurring banners, then the mirror sync above. Each validates and publishes only what it changed, and each runs whether or not the one before it passed, so an operator-data problem cannot hold back a Global key-art swap; a failed job still marks the whole run red. They run one after another rather than in parallel because `asset-manifest.json` is a single line, so two commits that both touch it cannot be rebased onto each other; each job starts from the branch tip, including the previous job's commit.
