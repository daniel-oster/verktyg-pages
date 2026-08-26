#!/usr/bin/env python3
"""Parsa en Travsport-startlista (officiell PDF) till JSON.

Travsport publicerar en fylligare startlista som PDF direkt på
`cdn.travsport.se/startlists/trot/<typ>/<raceday_id>.pdf` (t.ex.
`.../trot/russ/32667.pdf`) -- till skillnad från xlsx-nedladdningen
(se `parse_startlist.py`) går den att hämta direkt, utan captcha, och
innehåller mer: härstamning, uppfödare, dräkt/färger, loppvillkor och
de senaste starterna per häst.

PDF:en är genererad av Oracle Reports och layoutar varje lopp som en
tabell med hästar i två spalter (vänster/höger halva av sidan). Varje
hästblock har en fast radhöjd och innehåller flera undertexter på
kända x/y-positioner. Det här skriptet utnyttjar det: det hittar varje
hästs "namnrad" (fet 8pt-text i spaltens vänsterkant, följd av ett
"distans:spår"-token som "1640:1") och skär sedan ut allt som hör till
den hästen fram till nästa namnrad.

De sista fem starterna per häst plockas ut som råa textrader (`form`)
snarare än fullt uppdelade fält -- koderna där (bankoder, placeringar,
"c c"/"- -", marginaler) kräver mer källforskning för att tolkas
säkert, se GLOSSARY.md.

Exempel:

    python parse_startlist_pdf.py 32667.pdf --out romme.json

    # Hämta direkt från Travsport (kräver nätverksåtkomst)
    python parse_startlist_pdf.py --url https://cdn.travsport.se/startlists/trot/russ/32667.pdf --out romme.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

import pdfplumber

DIST_POST_RE = re.compile(r"^\*?(\d+):(\d+)$")
MONEY_RE = re.compile(r"^\d{1,3}(?:\.\d{3})*$")
TRAINER_RE = re.compile(r"^(.*?)\s*(?:\(([^()]+)\))?$")
AMATEUR_SUFFIX_RE = re.compile(r"\s+a$")
SEX_MAP = {"s": "sto", "v": "valack", "h": "hingst"}


def fetch_pdf(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def group_lines(words: list[dict], y_tol: float = 1.5) -> list[list[dict]]:
    """Gruppera ord som ligger på samma rad (närliggande 'top') och sortera efter x."""
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: w["top"]):
        if rows and abs(rows[-1][0]["top"] - w["top"]) <= y_tol:
            rows[-1].append(w)
        else:
            rows.append([w])
    for row in rows:
        row.sort(key=lambda w: w["x0"])
    return rows


def line_text(row: list[dict]) -> str:
    return " ".join(w["text"] for w in row)


def find_name_starts(words: list[dict], col_x0: float) -> list[dict]:
    """Hitta varje hästs namnrad: fet 8pt-text i spaltens vänsterkant med ett
    'distans:spår'-token (t.ex. '1640:3') någonstans på samma rad."""
    candidates = [
        w
        for w in words
        if "Bold" in w["fontname"]
        and 7.5 <= w["size"] <= 8.5
        and abs(w["x0"] - col_x0) < 3
    ]
    starts = []
    for c in candidates:
        same_row = [w for w in words if abs(w["top"] - c["top"]) <= 1.0]
        if any(DIST_POST_RE.match(w["text"]) for w in same_row):
            starts.append(c)
    starts.sort(key=lambda w: w["top"])
    return starts


def parse_horse_block(block_words: list[dict], col_x0: float) -> dict:
    header_words = [w for w in block_words if abs(w["top"] - min(w2["top"] for w2 in block_words)) <= 1.0]
    header_text = [w["text"] for w in sorted(header_words, key=lambda w: w["x0"])]
    dist_idx = next(i for i, t in enumerate(header_text) if DIST_POST_RE.match(t))
    name = " ".join(header_text[:dist_idx])
    dist_m, post = DIST_POST_RE.match(header_text[dist_idx]).groups()
    tail = header_text[dist_idx + 1 :]
    earnings_raw = tail[-1] if tail and MONEY_RE.match(tail[-1]) else None
    times = " ".join(tail[:-1] if earnings_raw else tail)
    earnings = int(earnings_raw.replace(".", "")) if earnings_raw else 0

    header_top = min(w["top"] for w in header_words)
    subcol_x = col_x0 + 134  # left edge of the recent-starts / stats sub-column
    desc_words = [w for w in block_words if w["top"] > header_top + 1 and w["x0"] < subcol_x]
    form_words = [w for w in block_words if w["top"] > header_top + 1 and w["x0"] >= subcol_x]

    desc_rows = group_lines(desc_words, y_tol=1.5)
    form_rows = group_lines(form_words, y_tol=1.5)

    sex = age = sire = dam = breeder = owner = silks = None
    driver = trainer = None
    driver_amateur = trainer_amateur = False

    for i, row in enumerate(desc_rows):
        text = line_text(row)
        if sire is None:
            m = re.match(r"^(\d+),\s*\S+\s+([svh])\s+e\s+(.+?)-?$", text)
            if m:
                age, sex_code, sire = m.groups()
                sex = SEX_MAP.get(sex_code, sex_code)
                continue
        elif dam is None and " e " in text:
            dam = text
            continue
        if text.startswith("Uppf:"):
            breeder = text[len("Uppf:") :].strip()
        elif text.startswith("Äg:"):
            owner = text[len("Äg:") :].strip()
            if i + 1 < len(desc_rows):
                silks = line_text(desc_rows[i + 1])
        elif i + 1 == len(desc_rows) and row[0]["fontname"].endswith("Arial,Bold"):
            is_amateur = bool(AMATEUR_SUFFIX_RE.search(text))
            text = AMATEUR_SUFFIX_RE.sub("", text)
            driver, trainer = TRAINER_RE.match(text).groups()
            if trainer:
                trainer_amateur = is_amateur
            else:
                driver_amateur = is_amateur

    stats = {"career": None, "this_year": None, "last_year": None}
    form: list[str] = []
    for i, row in enumerate(form_rows):
        text = line_text(row)
        if "Tot:" in text or re.search(r"^2[56]:", text):
            m = re.search(r"Tot:\s*(\d+)\s+([\d-]+)", text)
            if m:
                stats["career"] = {"starts": int(m.group(1)), "placements": m.group(2)}
            for label, key in (("26:", "this_year"), ("25:", "last_year")):
                m = re.search(rf"{label}\s*(\d+)\s+([\d-]+)\s+([\d,a]+)\s+([\d.]+)", text)
                if m:
                    stats[key] = {
                        "starts": int(m.group(1)),
                        "placements": m.group(2),
                        "best_time": m.group(3),
                        "earnings": int(m.group(4).replace(".", "")),
                    }
        else:
            form.append(text)

    return {
        "number": None,
        "name": name.rstrip("*"),
        "name_asterisk": name.endswith("*"),  # see GLOSSARY.md for what this marks
        "sex": sex,
        "age": int(age) if age else None,
        "sire": sire,
        "dam": dam,
        "breeder": breeder,
        "owner": owner,
        "silks": silks,
        "driver": driver,
        "driver_amateur": driver_amateur,
        "trainer": trainer,
        "trainer_amateur": trainer_amateur,
        "post": int(post),
        "distance_m": int(dist_m),
        "record_times": times,
        "earnings_sek": earnings,
        "stats": stats,
        "recent_form_raw": form[:5],
    }


def parse_race_header(page, table_top: float) -> dict:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False, extra_attrs=["size", "fontname"])
    header_words = [w for w in words if w["top"] < table_top]

    # The header has two visually separate columns: a small box (race number,
    # colour, start time, distance/start type, "Monté") on the far left, and
    # the race title + conditions text to its right. Group them separately so
    # lines that happen to sit close in y don't get merged across columns.
    box_words = [w for w in header_words if w["x0"] < 62 and w["top"] >= 5]
    text_words = [w for w in header_words if w["x0"] >= 62 and w["top"] >= 5]

    race_number = None
    color = None
    start_time = None
    distance_m = None
    start_type = None
    monte = False

    for row in group_lines(box_words, y_tol=1.0):
        text = line_text(row)
        if len(row) == 1 and row[0]["text"].isdigit() and row[0]["size"] >= 12:
            race_number = int(row[0]["text"])
            continue
        m = re.match(r"^ca kl (\d{1,2}:\d{2})$", text)
        if m:
            start_time = m.group(1)
            continue
        m = re.match(r"^(\d+) m(?:\s+(Auto|Volt))?$", text)
        if m:
            distance_m = int(m.group(1))
            if m.group(2):
                start_type = m.group(2)
            continue
        if text == "Monté":
            monte = True
            continue
        if len(row) == 1 and round(row[0]["size"], 1) == 8.0:
            color = text
            continue

    title = None
    condition_lines: list[str] = []
    prize_structure = None
    for row in group_lines(text_words, y_tol=2.0):
        text = line_text(row)
        sizes = {round(w["size"], 1) for w in row}
        if title is None and any(s >= 8.5 for s in sizes):
            title = text
            continue
        if text.startswith("Prispoäng:"):
            prize_structure = text[len("Prispoäng:") :].strip()
            continue
        condition_lines.append(text)

    return {
        "race_number": race_number,
        "title": title,
        "start_time": start_time,
        "distance_m": distance_m,
        "start_type": "Monté" if monte else start_type,
        "color": color,
        "conditions": " ".join(condition_lines),
        "prize_structure": prize_structure,
    }


def parse_page(page) -> dict:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False, extra_attrs=["size", "fontname"])

    left_starts = find_name_starts(words, col_x0=10.8)
    right_starts = find_name_starts(words, col_x0=405.2)
    if not left_starts:
        return None

    table_top = left_starts[0]["top"]
    race = parse_race_header(page, table_top)

    starters = []
    for col_starts, col_anchor, col_x1 in ((left_starts, 10.8, 400), (right_starts, 405.2, page.width)):
        col_x0 = col_anchor - 5
        for i, start in enumerate(col_starts):
            top0 = start["top"]
            top1 = col_starts[i + 1]["top"] if i + 1 < len(col_starts) else page.height
            block_words = [w for w in words if top0 - 0.5 <= w["top"] < top1 - 0.5 and col_x0 <= w["x0"] < col_x1]
            horse = parse_horse_block(block_words, col_anchor)
            starters.append(horse)

    starters.sort(key=lambda h: h["post"])
    for i, h in enumerate(starters, start=1):
        h["number"] = i

    race["starters"] = starters
    return race


def parse_startlist_pdf(path: Path) -> dict:
    with pdfplumber.open(path) as pdf:
        raceday_title = None
        races = []
        for page in pdf.pages:
            top_text = page.extract_text(x_tolerance=2) or ""
            first_line = top_text.split("\n", 1)[0] if top_text else ""
            if raceday_title is None and first_line:
                raceday_title = first_line
            race = parse_page(page)
            if race:
                races.append(race)
    return {"raceday": raceday_title, "races": races}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parsa en Travsport-startlista (officiell PDF) till JSON.")
    parser.add_argument("pdf", type=Path, nargs="?", help="Sökväg till startlist-PDF:en")
    parser.add_argument("--url", help="Hämta PDF:en från denna URL istället för en lokal fil")
    parser.add_argument("--out", type=Path, help="Skriv till denna fil istället för stdout")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    tmp_path: Path | None = None
    if args.url:
        data = fetch_pdf(args.url)
        fd, tmp_name = tempfile.mkstemp(suffix=".pdf")
        tmp_path = Path(tmp_name)
        with open(fd, "wb") as f:
            f.write(data)
        pdf_path = tmp_path
    elif args.pdf:
        pdf_path = args.pdf
    else:
        print("Ange antingen en PDF-fil eller --url.", file=sys.stderr)
        return 2

    if not pdf_path.exists():
        print(f"Hittar inte {pdf_path}", file=sys.stderr)
        return 2

    try:
        result = parse_startlist_pdf(pdf_path)
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)

    payload = json.dumps(result, ensure_ascii=False, indent=2)

    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(f"Skrev {args.out}", file=sys.stderr)
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
