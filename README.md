# verktyg-pages

Static GitHub Pages site publishing the output of
[`daniel-oster/verktyg`](https://github.com/daniel-oster/verktyg)'s
tools. First up: a startlist viewer for Swedish trotting racedays.

Deployed straight from this repo's `main` branch — enable it under
**Settings → Pages → Deploy from a branch → main / (root)** if it
isn't already.

## How it works

- `index.html` — the whole site: one static page, no build step, no
  framework. It fetches `data/manifest.json` to find available
  racedays, then `data/<slug>.json` for the selected one, and renders
  race cards you can click through to a starter list and then to a
  full-screen, plain-language breakdown of each horse.
- `data/` — the actual startlist data, as JSON. Committed to the repo
  (not fetched live) since `sportapp.travsport.se` itself is
  captcha-gated — see below.
- `scripts/` — vendored copy of `verktyg`'s
  `parse_startlist_pdf.py`, plus `fetch_raceday.py` which wraps it and
  updates `data/manifest.json`.

## Adding a new raceday

Easiest: go to **Actions → Uppdatera startlistor → Run workflow** and
fill in `url`, `slug`, `label`. It runs `fetch_raceday.py` and commits
the result straight to `main` — nothing to run locally.

To do it locally instead: find the raceday's PDF URL — the pattern is
`https://cdn.travsport.se/startlists/trot/<typ>/<raceday_id>.pdf`
(the `<raceday_id>` is the number from the `sportapp.travsport.se`
raceday URL, e.g. `tr32667` → `32667`) — then:

```
pip install -r scripts/requirements.txt
python scripts/fetch_raceday.py \
  --url https://cdn.travsport.se/startlists/trot/russ/32667.pdf \
  --slug romme-32667 \
  --label "Romme, söndag 30 augusti 2026"
```

Commit the updated `data/romme-32667.json` and `data/manifest.json`.
`index.html` itself doesn't need touching — it discovers racedays from
the manifest at runtime.

## Keeping data fresh automatically

`.github/workflows/update-startlists.yml` runs every 6 hours (and on
manual dispatch) and re-fetches every raceday already in
`data/manifest.json` via `scripts/refresh_all.py` — picks up late
scratches or driver changes between when a startlist was first added
and the actual raceday, and commits straight to `main` if anything
changed. Same workflow's manual-dispatch inputs (`url`/`slug`/`label`)
are also the way to add a brand-new raceday without touching a
terminal — see above.

## Keeping the vendored parser in sync

`scripts/parse_startlist_pdf.py` is a copy of the one in
`verktyg/travsport-startlist/`. Fix a bug in one, port it to the
other — nothing checks this automatically. See that repo's
`GLOSSARY.md` for what all the Swedish trotting abbreviations in the
data actually mean (kmtid notation, license categories, shoe/gallop
codes, etc.) — `index.html`'s natural-language explanations draw on
the same knowledge.
