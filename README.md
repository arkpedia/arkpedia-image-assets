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
