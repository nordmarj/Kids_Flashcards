#!/usr/bin/env python3
"""Check which candidate words have an image, a Swedish recording and an
English recording available.

Reads data/candidates/words.csv and writes data/candidates/coverage.csv.
Nothing is downloaded; this only looks the media up so we can pick words.

Sources (see CLAUDE.md):
  image    ARASAAC pictogram found by English keyword (pictures are language
           independent, so one lookup per concept is enough)
  audio    Lingua Libre recordings on Wikimedia Commons
           (File:LL-Q9027 (swe)-<speaker>-<word>.wav, LL-Q1860 (eng) for English),
           falling back to classic Commons files (Sv-<word>.ogg, En-us-<word>.ogg)

Usage: python3 scripts/check_coverage.py [--limit N] [--recheck]
"""

import argparse
import csv
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "data" / "candidates" / "words.csv"
OUTPUT = ROOT / "data" / "candidates" / "coverage.csv"

ARASAAC = "https://api.arasaac.org/v1/pictograms/en/bestsearch/{}"
COMMONS = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "Kids_Flashcards/0.1 (https://github.com/nordmarj/Kids_Flashcards; "
    "media coverage check)"
)
DELAY = 0.3  # seconds between requests, to stay well inside rate limits

LINGUA_LIBRE = {"sv": "LL-Q9027 (swe)", "en": "LL-Q1860 (eng)", "de": "LL-Q188 (deu)",
                "sw": "LL-Q7838 (swa)"}
COMMONS_FALLBACK = {"sv": ["Sv-{}.ogg"], "en": ["En-us-{}.ogg", "En-uk-{}.ogg", "En-au-{}.ogg"],
                    "de": ["De-{}.ogg"], "sw": ["Sw-ke-{}.flac"]}

session = requests.Session()
session.headers["User-Agent"] = USER_AGENT


def api_error(r):
    """True if the MediaWiki API answered 200 with an error body (e.g. throttled)."""
    if "json" not in r.headers.get("Content-Type", ""):
        return False
    try:
        return "error" in r.json()
    except ValueError:
        return False


def get(url, **params):
    """GET with a polite delay, backing off and retrying on 429/5xx and
    dropped connections."""
    for attempt in range(6):
        time.sleep(DELAY)
        try:
            r = session.get(url, params=params or None, timeout=30)
        except requests.ConnectionError as e:
            if attempt == 5:
                raise
            wait = 5 * 2**attempt
            print(f"  {type(e).__name__}, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if r.status_code != 429 and r.status_code < 500 and not api_error(r):
            return r
        wait = int(r.headers.get("Retry-After", 0) or 0) or 5 * 2**attempt
        print(f"  {r.status_code}, retrying in {wait}s", file=sys.stderr)
        time.sleep(wait)
    return r


def arasaac_ids(word):
    """ARASAAC pictogram ids whose English keyword best matches `word`."""
    r = get(ARASAAC.format(requests.utils.quote(word)))
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return [p["_id"] for p in r.json()]


def lingua_libre_pattern(lang, word):
    prefix = re.escape(LINGUA_LIBRE[lang])
    return re.compile(
        rf"^File:{prefix}-[^-]+-{re.escape(word)}\.(wav|ogg|flac|mp3)$", re.IGNORECASE
    )


def lingua_libre_files(lang, word):
    """Commons titles of Lingua Libre recordings of exactly `word`."""
    r = get(
        COMMONS,
        action="query",
        list="search",
        srnamespace=6,
        srlimit=50,
        format="json",
        srsearch=f'intitle:"{LINGUA_LIBRE[lang]}" intitle:"{word}"',
    )
    r.raise_for_status()
    pattern = lingua_libre_pattern(lang, word)
    return [h["title"] for h in r.json()["query"]["search"] if pattern.match(h["title"])]


def commons_fallback_files(lang, word):
    """Classic Commons pronunciation files that exist for `word`."""
    titles = ["File:" + t.format(word) for t in COMMONS_FALLBACK[lang]]
    r = get(COMMONS, action="query", format="json", titles="|".join(titles))
    r.raise_for_status()
    pages = r.json()["query"]["pages"].values()
    return [p["title"] for p in pages if "missing" not in p]


def check(row):
    out = dict(row)
    ids = arasaac_ids(row["en"] or row["sv"])
    out["arasaac_ids"] = " ".join(map(str, ids[:5]))
    have = {"image": bool(ids)}
    for lang in ("sv", "en"):
        # A word may be listed in only one language; the other is not needed.
        if not row[lang]:
            continue
        ll = lingua_libre_files(lang, row[lang])
        fb = [] if ll else commons_fallback_files(lang, row[lang])
        out[f"ll_{lang}"] = len(ll)
        out[f"ll_{lang}_example"] = ll[0] if ll else ""
        out[f"commons_{lang}"] = " ".join(fb)
        have[f"audio_{lang}"] = bool(ll or fb)
    missing = [k for k, v in have.items() if not v]
    out["status"] = "complete" if not missing else "missing " + "+".join(missing)
    return out


def write(results):
    with OUTPUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(results)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, help="only check the first N words")
    ap.add_argument("--recheck", action="store_true", help="look up words already in coverage.csv again")
    args = ap.parse_args()

    with CANDIDATES.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))[: args.limit]

    # Words already checked keep their result unless --recheck is given, so
    # adding words to words.csv only costs lookups for the new ones.
    done = {}
    if OUTPUT.exists() and not args.recheck:
        with OUTPUT.open(encoding="utf-8") as f:
            done = {r["id"]: r for r in csv.DictReader(f)}

    results = []
    for i, row in enumerate(rows, 1):
        res = done.get(row["id"]) or check(row)
        results.append(res)
        print(f"[{i}/{len(rows)}] {row['id']}: {res['status']}", file=sys.stderr)
        if row["id"] not in done:
            # Save as we go, so an interrupted run keeps what it found.
            write(results + [r for r in done.values() if r["id"] not in {x["id"] for x in results}])

    write(results)

    complete = sum(r["status"] == "complete" for r in results)
    print(f"{complete}/{len(results)} words have image + sv audio + en audio")
    for key in ("image", "audio_sv", "audio_en"):
        n = sum(key in r["status"] for r in results)
        print(f"  missing {key}: {n}")


if __name__ == "__main__":
    main()
