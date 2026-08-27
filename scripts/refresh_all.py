#!/usr/bin/env python3
"""Kör om fetch_raceday.py för alla travdagar som redan finns i data/manifest.json.

Tänkt att köras periodiskt (se .github/workflows/update-startlists.yml)
för att hålla redan tillagda travdagar färska — t.ex. om en häst
stryks eller en kusk byts ut mellan att startlistan först hämtades och
själva tävlingsdagen. Lägger INTE till nya travdagar; det görs med
`fetch_raceday.py --url ... --slug ... --label ...` (manuellt, eller
via workflow_dispatch-inputs på samma workflow).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = SCRIPT_DIR.parent / "data" / "manifest.json"


def main() -> int:
    if not MANIFEST_PATH.exists():
        print("Ingen data/manifest.json hittades, inget att uppdatera.", file=sys.stderr)
        return 0

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ok = True
    for entry in manifest:
        if not entry.get("source_url"):
            print(f"Hoppar över {entry.get('slug')}: ingen source_url sparad.", file=sys.stderr)
            continue
        print(f"Uppdaterar {entry['slug']}...", file=sys.stderr)
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "fetch_raceday.py"),
                "--url", entry["source_url"],
                "--slug", entry["slug"],
                "--label", entry["label"],
            ]
        )
        if result.returncode != 0:
            print(f"Misslyckades att uppdatera {entry['slug']}", file=sys.stderr)
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
