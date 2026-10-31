# docs/site - the Legends Classic landing page

`index.html` is the whole site: one self-contained page with inline CSS, no external scripts, fonts or CDNs, light
and dark themes from the system setting (`prefers-color-scheme`), and a layout that works at phone width. It links to
the repositories, the docs on GitHub and the Discord; it never links to game content.

## Before you publish: screenshots and the banner

The page has six screenshot slots and a banner slot. **The image files are not in the repository yet.** Until a file
exists, its slot shows a striped "Screenshot to come" box, so the page can go live without them.

| File | Used by |
|---|---|
| `docs/site/img/banner.png` | the `<!-- banner: img/banner.png -->` comment above the wordmark (not wired up yet: add an `<img>` there when the banner exists) |
| `docs/site/img/shot-01.png` ... `shot-06.png` | the six `<figure>` slots in the Screenshots section, in order |

When a screenshot goes in, also replace its `TODO` alt text and caption in `index.html`. The slots are 16:9; a 4:3
shot is letterboxed, not cropped. Keep each file well under 1 MiB (the content guard's size limit), for example
1600x900 PNG or a JPEG (then change the `src` extension).

**This needs a decision first.** The content guard (`tools/check_no_game_content.py`) rejects every image as `MEDIA`
("screenshots and textures are game imagery"), `.content-guard-allow` says "no MEDIA entries (no screenshots in
git)", and LEGAL.md says the repository contains "no game art". Committing screenshots therefore means changing that
policy on purpose: either add one `MEDIA` allowlist entry per file with its reason, or keep the screenshots out of
`main` (for example only on the `gh-pages` branch of option B below - that branch is still part of the repository, so
LEGAL.md's wording applies to it too). A banner made from original art (no official logos, box art, key art or
character art) fits the guard's rule as it is: "original art must be allowlisted".

## Publishing with GitHub Pages

GitHub's "Deploy from a branch" can only serve a branch's root or its `/docs` folder, not `/docs/site`. Serving
`/docs` would publish the whole docs folder, so use one of these two ways instead.

### Option A: a Pages workflow that publishes docs/site (recommended)

1. Add `.github/workflows/pages.yml`:

   ```yaml
   name: pages
   on:
     push:
       branches: [main]
       paths: ["docs/site/**"]
     workflow_dispatch:
   permissions:
     contents: read
     pages: write
     id-token: write
   concurrency:
     group: pages
     cancel-in-progress: true
   jobs:
     deploy:
       runs-on: ubuntu-latest
       environment:
         name: github-pages
         url: ${{ steps.deployment.outputs.page_url }}
       steps:
         - uses: actions/checkout@v7
         - uses: actions/configure-pages@v5
         - uses: actions/upload-pages-artifact@v3
           with:
             path: docs/site
         - id: deployment
           uses: actions/deploy-pages@v4
   ```

   Check the action versions against the ones the other workflows in `.github/workflows` use before committing it.
   It runs only when `docs/site` changes on `main` (or by hand), so it costs few Actions minutes.
2. On GitHub: **Settings > Pages > Build and deployment > Source: GitHub Actions**.
3. Push to `main` (or run the workflow by hand). The site appears at `https://chronorixun.github.io/legends-classic/`.

This publishes the folder as it is, without Jekyll; this README is published too (as a plain `.md` file). The content
guard workflow keeps running on every push as before.

### Option B: a gh-pages branch

1. Check the folder, then push a branch whose root is `docs/site` (made from the committed history of that folder):

   ```sh
   python tools/check_no_game_content.py docs/site
   git push origin "$(git subtree split --prefix docs/site HEAD):refs/heads/gh-pages"
   ```

   Run the same two commands after every committed change to `docs/site`; the split is repeatable, so each push is a
   fast-forward of the same branch.
2. On GitHub: **Settings > Pages > Build and deployment > Source: Deploy from a branch**, branch `gh-pages`, folder
   `/ (root)`.

The `gh-pages` branch has no `.github/workflows` or `tools/` folder, so the content guard CI does not run on it: run
the guard on `docs/site` yourself before each push (step 1 does). GitHub runs Jekyll on this branch; it copies
`index.html` unchanged. Add an empty `.nojekyll` file to `docs/site` to turn Jekyll off.

## Keeping it current

Lines that change with each release carry `<!-- release round: update -->` (the release line, the online co-op card,
the online limit and the roadmap), the same marker the README and docs use. Every fact on the page comes from
README.md, docs/ROADMAP.md, docs/KNOWN-ISSUES.md, docs/ONLINE.md and LEGAL.md; update the page when they change, and
don't add claims they don't make.
