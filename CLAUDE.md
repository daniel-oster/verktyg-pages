# verktyg-pages

Static GitHub Pages site (deployed from `main`) publishing tools from
[`daniel-oster/verktyg`](https://github.com/daniel-oster/verktyg) as
actual web pages. `verktyg` itself is CLI/data-only by design (see its
CLAUDE.md) — this repo is where that data gets a UI.

## Current page: Travsport startlist viewer

`index.html` is the entire site — one static file, vanilla JS, no
build step. It fetches `data/manifest.json` (list of racedays) and
`data/<slug>.json` (the actual startlist, produced by
`scripts/parse_startlist_pdf.py`) at runtime and renders:

- a grid of race cards (click → expands in place to a starter table)
- click a horse row → full-screen overlay with a plain-language
  explanation of every field on that horse's line, decoded using the
  trav terminology explained in `verktyg`'s
  `travsport-startlist/GLOSSARY.md`
- a driver-name filter that's specifically there to surface
  **Annabelle Öster**'s races (this was a deliberate ask, not a demo
  feature — keep it working when touching the filter/search logic)

## Data pipeline

`sportapp.travsport.se`'s own startlist page is captcha-gated, but
Travsport separately publishes a fuller official PDF per raceday at
`cdn.travsport.se/startlists/trot/<typ>/<raceday_id>.pdf` with no
captcha. `scripts/fetch_raceday.py` downloads and parses that PDF and
writes/updates `data/<slug>.json` + `data/manifest.json`. Run it to
add a new raceday — see README.md for the exact command. `index.html`
never regenerates; it just reads whatever's in `data/`.

## Vendoring

`scripts/parse_startlist_pdf.py` is a copy of
`verktyg/travsport-startlist/parse_startlist_pdf.py`. Keep them in
sync by hand — fix a bug in one, port it to the other, same as
`verktyg` does with its own vendored copies in the `schema` repo.

## Design language

Editorial/program-sheet feel (this is styled after an actual printed
travprogram): "Big Shoulders Display" for headings, "IBM Plex Sans"
for body copy, "IBM Plex Mono" for numbers/times. The per-race colour
badge (Gul/Blå/Grön/...) comes straight from the PDF's own printed
race colour — it's real information, not decoration, so don't drop it
in a redesign. Full light/dark theme support via CSS custom
properties — test both when changing colors.
