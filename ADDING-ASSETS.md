# Adding an image by hand

Nothing here needs a hash typed by hand. Every SHA in this repository and in the
website's config is computed by a script; if you find yourself copying one, stop,
because something has gone wrong.

## Where the hashes come from, and why there are three of them

| File | Holds | Written by |
| --- | --- | --- |
| `asset-manifest.json` (here) | one `{bytes, sha256}` row per image | `scripts/sync_images.py` for mirrored art, `scripts/add_local_assets.py` for hand-added art |
| `data/assets/revisions.json` (app) | the commit SHA of each asset repo | `npm run assets:update` |
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

   Once listed, an icon or portrait is yours: the daily mirror sync refreshes only
   paths in `asset-source-map.json`, and its operator and enemy discovery skip anything the
   manifest already lists, so it never re-fetches a hand-added file over yours. The
   exception is an event poster or banner image entering its Global window, which
   the key-art job replaces with the English upload.

3. Commit the image and `asset-manifest.json` together, and push. CI runs
   `scripts/validate_images.py`, which decodes every image and checks it against
   its row, so a bad file fails here rather than showing up blank on the site.

4. In the website repository, adopt the new commit:

   ```bash
   npm run assets:update
   npm run check:assets
   ```

   `assets:update` reads each asset repository's current commit SHA from the GitHub
   API and rewrites `data/assets/revisions.json` and the two asset indexes for you.
   `check:assets` then confirms every icon path the game records imply resolves to a
   published file — that check is what catches a filename that does not match what
   the site will ask for. Commit those files together.

5. Publish. Either wait for the daily **Prepare content release** run, or start it by
   hand from the website repository's Actions tab (Run workflow, leave the defaults).
   It opens a PR on `arkpedia-data`; merging that PR publishes the release, and the
   site picks it up within about a minute. No website deployment is involved.

## If the name is wrong

The site builds the filename from the record, so a mismatch is a blank square and
nothing logs it. `npm run check:assets` in the website repository is the check that
names the exact path it expected. Rename the file to match, or fix the record —
whichever is actually wrong — rather than adding a second copy.

## Rolling back

Revert the commit here, then run `npm run assets:update` again in the website
repository and publish. To undo a published release without touching this
repository at all, run **Content release** on `arkpedia-data` by hand with an
earlier approved commit SHA; only the live pointer moves.
