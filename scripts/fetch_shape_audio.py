#!/usr/bin/env python3
"""Find and download recordings of the shape names in data/shapes/shapes.csv.

For each shape and language:
  - if a word deck already has a recording of exactly that word, reuse it;
  - otherwise take a Lingua Libre recording (preferring the speakers the word
    decks already use, so the decks sound alike), else a classic Commons
    pronunciation file, and download it as media/audio/<lang>/shape_<id>_<lang>.mp3
    with a provenance row in media/sources.csv;
  - if no recording exists, leave the audio column empty (the card stays silent).

Writes the audio_sv / audio_en columns of data/shapes/shapes.csv. Shapes that
already have audio are skipped, so reruns only look up the gaps.

Usage: python3 scripts/fetch_shape_audio.py
"""

import collections
import csv
import datetime
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_coverage import commons_fallback_files  # noqa: E402
from fetch_media import (  # noqa: E402
    ACCEPTABLE,
    CONCEPTS,
    MEDIA,
    PICKS,
    SOURCE_FIELDS,
    SOURCES,
    commons_info,
    download_file,
    lingua_libre_recordings,
    sha256,
    to_mono_mp3,
    transcoded_mp3,
)

ROOT = Path(__file__).resolve().parent.parent
SHAPES = ROOT / "data" / "shapes" / "shapes.csv"
SHAPE_FIELDS = ["id", "sv", "en", "level", "audio_sv", "audio_en"]
LANGS = ("sv", "en")


def existing_recordings():
    """{(lang, word): audio file name} from the word decks' concept tables."""
    found = {}
    for path in CONCEPTS.glob("*.csv"):
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                for lang in LANGS:
                    if row.get(f"audio_{lang}"):
                        found.setdefault((lang, row[lang]), row[f"audio_{lang}"])
    return found


def speaker_rank():
    rank = {lang: collections.Counter() for lang in LANGS}
    with PICKS.open(encoding="utf-8", newline="") as f:
        for p in csv.DictReader(f):
            for lang in LANGS:
                m = re.match(r"File:LL-Q\d+ \(\w+\)-([^-]+)-", p[f"audio_{lang}_title"])
                if m:
                    rank[lang][m.group(1)] += 1
    return rank


def find_title(lang, word, rank):
    ll = lingua_libre_recordings(lang, word)
    if ll:
        return ll[max(ll, key=lambda s: rank[lang][s])]
    fallback = commons_fallback_files(lang, word)
    return fallback[0] if fallback else ""


def main():
    with SHAPES.open(encoding="utf-8", newline="") as f:
        shapes = list(csv.DictReader(f))
    with SOURCES.open(encoding="utf-8", newline="") as f:
        sources = {row["file"]: row for row in csv.DictReader(f)}

    reuse = existing_recordings()
    rank = speaker_rank()
    titles = {}  # (shape id, lang) -> Commons title to download
    for s in shapes:
        for lang in LANGS:
            key = f"audio_{lang}"
            if s.get(key):
                continue
            if (lang, s[lang]) in reuse:
                s[key] = reuse[(lang, s[lang])]
                continue
            title = find_title(lang, s[lang], rank)
            print(f"{s['id']} {lang}: {title or 'no recording'}", file=sys.stderr)
            if title:
                titles[(s["id"], lang)] = title
            s[key] = ""

    info = commons_info(set(titles.values()))
    today = datetime.date.today().isoformat()
    by_id = {s["id"]: s for s in shapes}
    for (sid, lang), title in titles.items():
        url, page, author, licence, licence_url = info[title]
        if not ACCEPTABLE.match(licence):
            print(f"{sid} {lang}: {title} has licence {licence!r}, skipped", file=sys.stderr)
            continue
        dest = MEDIA / "audio" / lang / f"shape_{sid}_{lang}.mp3"
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "original.mp3"
            download_file(transcoded_mp3(url), raw)
            to_mono_mp3(raw, dest)
        rel = f"audio/{lang}/{dest.name}"
        sources[rel] = dict(zip(SOURCE_FIELDS, [
            rel, "Lingua Libre" if title.startswith("File:LL-") else "Wikimedia Commons",
            page, author, licence, licence_url, today, sha256(dest)]))
        by_id[sid][f"audio_{lang}"] = dest.name

    with SOURCES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SOURCE_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(sources.values(), key=lambda r: r["file"]))
    with SHAPES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SHAPE_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows({k: s.get(k, "") for k in SHAPE_FIELDS} for s in shapes)

    for lang in LANGS:
        n = sum(1 for s in shapes if s[f"audio_{lang}"])
        print(f"{lang}: {n}/{len(shapes)} shapes have audio")


if __name__ == "__main__":
    main()
