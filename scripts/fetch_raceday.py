#!/usr/bin/env python3
"""Hämta en Travsport-startlista och lägg till/uppdatera den i data/.

Kör detta varje gång en ny travdag ska publiceras på sidan. Skriver
`data/<slug>.json` (själva startlistan, från `parse_startlist_pdf.py`)
och uppdaterar `data/manifest.json` (listan över travdagar sidan visar
i väljaren).

Exempel:

    python scripts/fetch_raceday.py \
        --url https://cdn.travsport.se/startlists/trot/russ/32667.pdf \
        --slug romme-32667 \
        --label "Romme, söndag 30 augusti 2026"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from parse_startlist_pdf import fetch_pdf, parse_startlist_pdf

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANIFEST_PATH = DATA_DIR / "manifest.json"


def load_manifest() -> list[dict]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return []


def save_manifest(entries: list[dict]) -> None:
    entries.sort(key=lambda e: e["label"])
    MANIFEST_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hämta en travdag och lägg till den på sidan.")
    parser.add_argument("--url", help="URL till startlist-PDF:en på cdn.travsport.se")
    parser.add_argument("--pdf", type=Path, help="...eller en redan nedladdad PDF-fil")
    parser.add_argument("--slug", required=True, help="Filnamn för datat, t.ex. 'romme-32667'")
    parser.add_argument("--label", required=True, help="Namn i travdags-väljaren, t.ex. 'Romme, söndag 30 augusti 2026'")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.url:
        import tempfile

        data = fetch_pdf(args.url)
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(data)
            tmp.flush()
            result = parse_startlist_pdf(Path(tmp.name))
    elif args.pdf:
        result = parse_startlist_pdf(args.pdf)
    else:
        print("Ange --url eller --pdf.", file=sys.stderr)
        return 2

    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"{args.slug}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Skrev {out_path}", file=sys.stderr)

    manifest = load_manifest()
    manifest = [e for e in manifest if e["slug"] != args.slug]
    manifest.append({"slug": args.slug, "label": args.label, "file": out_path.name, "source_url": args.url})
    save_manifest(manifest)
    print(f"Uppdaterade {MANIFEST_PATH}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
