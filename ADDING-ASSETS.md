# Adding an image by hand

Nothing here needs a hash typed by hand. Every SHA in this repository and in the
website's config is computed by a script; if you find yourself copying one, stop,
because something has gone wrong.

## Where the hashes come from, and why there are three of them

| File | Holds | Written by |
| --- | --- | --- |
| `asset-manifest.json` (here) | each image's bytes, SHA-256 and dimensions | `scripts/sync_images.py` for mirrored art, `scripts/add_local_assets.py` for hand-added art, the website's content release (`publish-catalogue-assets.py`) for the art it imports (see the README) |
| `data/assets/revisions.json` (app/compiler checkout) | the commit SHA of each asset repo | `npm run assets:update`, also run by content preparation |
| `release/manifest.json` (arkpedia-data) | the same commit SHAs, plus a hash per page | the content release job |

They exist so that one page load cannot mix art from two different versions: a page
renders against one release, and that release names one commit of this repository.
That is also why the site does not simply point at `main` — a push here would change
what an already-open page is loading.

## Adding art

1. Put the file in its delivery folder under the name the site asks for. The
   convention is `<Operator> - <Thing>.webp`, using **our** English name, e.g.
   `base-skill-icons/Ripresa - Professional Manager α.webp`. Skill and base-skill
   icons are 64x64 RGB flattened onto **white**; operator and skin art is RGBA.

2. Enter it in the manifest:

   ```bash
   python scripts/add_local_assets.py
   ```

   It measures every image on disk that is not listed yet and adds a row. It never
   touches an existing row — use `--replace <path>` to deliberately re-measure one,
   and `--dry-run` to see what it would do first.

   What the daily mirror sync does with a listed file depends on its row in
   `asset-source-map.json`:

   - **No row:** never touched. Operator and enemy discovery skip anything the
     manifest already lists, so they never add a row for it.
   - **A row without `sourceBlob`** (a manual row, or one the app's catalogue import
     wrote with its file): adopted. The sync records the current upstream blob and
     leaves the file as it is, and the row then falls under the next case. Only a
     target the manifest does not list is fetched, so to have the mirror replace a
     hand-added file, delete the file and its manifest row instead.
   - **A row with `sourceBlob`:** the mirror's. When the upstream blob changes, the
     file is fetched and re-encoded over whatever is there, including a correction
     made with `--replace`. To keep such a correction, delete its row from
     `asset-source-map.json` in the same commit.

   The other exception is an event poster or banner image entering its Global
   window, which the key-art job replaces with the English upload.

3. Record the original URL and source-byte hash in the appropriate `sources/`
   catalogue, following the existing importer or folder convention. Commit the image,
   manifest and provenance together for review. CI runs
   `scripts/validate_images.py`, which decodes every image and checks it against
   its row, so a bad file fails here rather than showing up blank on the site. Merge
   the reviewed change to this repository's `main` before preparing a release.

4. Publish through the website repository's **Prepare content release** workflow.
   Wait for its scheduled run or start it on app `main`, normally using data `main`
   with upstream refresh enabled. Preparation resolves asset heads and validates the
   matching availability indexes before compiling the data release. A manual app
   pin commit is not required for a normal media-only update.

   For local inspection, the same adoption and coverage checks are available:

   ```bash
   npm run assets:update
   npm run check:assets
   ```

   `assets:update` reads each asset repository's current commit SHA from the GitHub
   API/git and rewrites `data/assets/revisions.json` and the two asset indexes for you.
   `check:assets` then confirms every icon path the game records imply resolves to a
   published file — that check is what catches a filename that does not match what
   the site will ask for. If an app change deliberately commits these generated pin
   files, review and commit all three together.

5. Verify publication. Normal preparation pushes the compiled release directly to
   `arkpedia-data/main` as a fast-forward. That repository's **Content release**
   workflow validates it before moving `live/current.json`; a failed check leaves
   readers on the previous release. No data PR is required for this path. The
   separate `refresh/content` branch still supports the reviewed-PR workflow.

   Check that the live manifest pins the intended image revision and that the
   affected page requests that pinned URL and displays the art. Content and media
   updates are adopted after cache refresh without rebuilding the website; a page
   already open keeps its existing version. App structure changes have their own
   deployment step. See the current [data publication contract](https://github.com/arkpedia/arkpedia-data#updating-content).

## If the name is wrong

The site builds the filename from the record, so a mismatch is a blank square and
nothing logs it. `npm run check:assets` in the website repository is the check that
names the exact path it expected. Rename the file to match, or fix the record —
whichever is actually wrong — rather than adding a second copy.

## Removing published art

arkpedia/arkpedia's daily pin step refuses to adopt a commit that stops publishing a path it published before, so a broken manifest can never empty the site's art. To remove a file on purpose, in the same PR:

1. Delete the file, its `asset-manifest.json` row and any `sources/*.json` record.
2. Add the path to `retired-assets.json` with the reason, e.g. `"headhunting-banner-images/Standard Pool 177 (Global).webp": { "reason": "a stand-in, not the official art", "removed": "#33" }`.

`validate_images.py` fails if a retired path is still published. The site then shows no art for that path (a page that names it falls back), until a new file is published under the same path; remove its `retired-assets.json` entry in that PR.

## Rolling back

Revert the commit here through a reviewed change, then prepare and verify a new
content release. To undo a published release without touching this
repository at all, run **Content release** on `arkpedia-data` by hand with an
earlier approved commit SHA; only the live pointer moves.

### Case-insensitive checkouts

New media paths must also be unique after Unicode normalization and case folding, including folder names. The complete inventory check enforces this in full and staged validation. Keep a region/original variant under an explicitly different path; changing only letter case cannot distinguish artwork on a case-insensitive checkout.

The existing `one-star-icons/Gallus² - Base.webp` / `GALLUS² - Base.webp` pair is a documented exception with different bytes. Both published files remain intact pending a consumer/provenance migration. Do not delete either to make a macOS checkout appear clean. The validator rejects new collisions and stale exceptions once a reviewed migration removes a pair.
