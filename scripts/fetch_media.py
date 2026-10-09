#!/usr/bin/env python3
"""Pick and download the picture and recordings for each concept.

Two steps, so the choices can be reviewed (and edited by hand) before
anything is downloaded:

  pick      For every word marked complete in data/candidates/coverage.csv,
            choose an ARASAAC pictogram and a recording in each language
            the word has, and write them to data/candidates/media_picks.csv.
            A word may have only Swedish or only English (leave the other
            language's word and recording title empty); it then only
            appears in that language's deck.
            Recordings by the speaker who recorded most of the words are
            preferred, so a deck sounds like one voice. Words already in
            media_picks.csv are kept as they are; to swap a picture, edit
            its arasaac_id, and to drop a word, blank its arasaac_id.
  download  Download everything in media_picks.csv that isn't in media/ yet,
            record provenance in media/sources.csv and write
            data/concepts/<topic>.csv.

Usage: python3 scripts/fetch_media.py pick|download [--limit N]
"""

import argparse
import collections
import csv
import datetime
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_coverage import (  # noqa: E402
    COMMONS,
    LINGUA_LIBRE,
    arasaac_ids,
    commons_fallback_files,
    get,
)
from word_decks import LANGUAGES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COVERAGE = ROOT / "data" / "candidates" / "coverage.csv"
PICKS = ROOT / "data" / "candidates" / "media_picks.csv"
CONCEPTS = ROOT / "data" / "concepts"
MEDIA = ROOT / "media"
SOURCES = MEDIA / "sources.csv"

ARASAAC_META = "https://api.arasaac.org/v1/pictograms/en/{}"
ARASAAC_PNG = "https://static.arasaac.org/pictograms/{0}/{0}_500.png"
ARASAAC_PAGE = "https://arasaac.org/pictograms/en/{}"
ARASAAC_AUTHOR = "Sergio Palao, ARASAAC (Government of Aragón)"
CC_BY_NC_SA = ("CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/")

LANGS = list(LANGUAGES)
PICK_FIELDS = (["id", "topic", *LANGS, "level", "arasaac_id"]
               + [f"audio_{lang}_title" for lang in LANGS])
CONCEPT_FIELDS = ["id", *LANGS, "level", "image"] + [f"audio_{lang}" for lang in LANGS]
SOURCE_FIELDS = ["file", "source", "source_url", "author", "licence", "licence_url", "retrieved_at", "sha256"]


# ---------------------------------------------------------------- pick


def lingua_libre_recordings(lang, word):
    """{speaker: title} of Lingua Libre recordings of exactly `word`.

    The speaker part may not contain a hyphen, so compounds such as
    "half-moon" or "e-book" are not taken for "moon" or "book".
    """
    prefix = re.escape(LINGUA_LIBRE[lang])
    pattern = re.compile(
        rf"^File:{prefix}-([^-]+)-{re.escape(word)}\.(wav|ogg|flac|mp3)$", re.IGNORECASE
    )
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
    found = {}
    for hit in r.json()["query"]["search"]:
        m = pattern.match(hit["title"])
        if m:
            found.setdefault(m.group(1), hit["title"])
    return found


def child_safe(pictogram_id):
    r = get(ARASAAC_META.format(pictogram_id))
    r.raise_for_status()
    meta = r.json()
    return not (meta.get("sex") or meta.get("violence"))


def languages(pick):
    """Languages a pick has both a word and a recording for."""
    return [lang for lang in LANGS if pick.get(lang) and pick.get(f"audio_{lang}_title")]


def complete(pick):
    """A pick needs a picture and at least one language with its recording."""
    return all(pick[k] for k in ("id", "topic", "level", "arasaac_id")) and bool(languages(pick))


def pick(limit):
    with COVERAGE.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["status"] == "complete"][:limit]

    # Keep earlier picks (they may be hand-edited and their media is already
    # downloaded); only new complete words are looked up.
    kept = []
    if PICKS.exists():
        with PICKS.open(encoding="utf-8") as f:
            kept = list(csv.DictReader(f))
    known = {p["id"] for p in kept}
    rows = [r for r in rows if r["id"] not in known]

    # Prefer the speaker who has recorded the most of our words, so a deck
    # sounds like one voice: count speakers of earlier picks and of every
    # recording found so far.
    rank = {"sv": collections.Counter(), "en": collections.Counter()}
    for p in kept:
        for lang in ("sv", "en"):
            m = re.match(r"File:LL-Q\d+ \(\w+\)-([^-]+)-", p[f"audio_{lang}_title"])
            if m:
                rank[lang][m.group(1)] += 2

    picks = list(kept)
    for i, row in enumerate(rows, 1):
        out = {k: row[k] for k in ("id", "topic", "sv", "en", "level")}
        out["arasaac_id"] = next((p for p in arasaac_ids(row["en"]) if child_safe(p)), "")
        for lang in ("sv", "en"):
            if not row[lang]:
                out[f"audio_{lang}_title"] = ""
                continue
            ll = lingua_libre_recordings(lang, row[lang])
            rank[lang].update(ll.keys())
            if ll:
                speaker = max(ll, key=lambda s: rank[lang][s])
                out[f"audio_{lang}_title"] = ll[speaker]
            else:
                fallback = commons_fallback_files(lang, row[lang])
                out[f"audio_{lang}_title"] = fallback[0] if fallback else ""
        picks.append(out)
        # Save after every word, so an interrupted run resumes where it stopped.
        with PICKS.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=PICK_FIELDS, restval="", lineterminator="\n")
            w.writeheader()
            w.writerows(picks)
        print(f"[{i}/{len(rows)}] {row['id']}", file=sys.stderr)

    gaps = [p["id"] for p in picks if not complete(p)]
    print(f"wrote {len(picks)} picks ({len(rows)} new) to {PICKS.relative_to(ROOT)}")
    if gaps:
        print("no longer complete (left out of download): " + ", ".join(gaps))


# ---------------------------------------------------------------- download


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strip_html(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return "; ".join(line.strip() for line in text.splitlines() if line.strip())


def commons_info(titles):
    """{title: (download url, page url, author, licence, licence url)}."""
    info = {}
    titles = list(titles)
    for start in range(0, len(titles), 50):
        r = get(
            COMMONS,
            action="query",
            format="json",
            prop="imageinfo",
            iiprop="url|extmetadata|user",
            titles="|".join(titles[start : start + 50]),
        )
        r.raise_for_status()
        query = r.json()["query"]
        # The API normalises titles (e.g. first letter, Unicode); map them back.
        back = {n["to"]: n["from"] for n in query.get("normalized", [])}
        for page in query["pages"].values():
            if "imageinfo" not in page:
                continue
            ii = page["imageinfo"][0]
            meta = ii.get("extmetadata", {})
            value = lambda key: strip_html(meta.get(key, {}).get("value", ""))  # noqa: E731
            info[back.get(page["title"], page["title"])] = (
                ii["url"],
                ii["descriptionurl"],
                # Older Sv-/En- files often lack an Artist field; credit the
                # uploader then, since CC BY(-SA) requires attribution.
                value("Artist") or ii.get("user", "").replace("~commonswiki", ""),
                value("LicenseShortName"),
                value("LicenseUrl"),
            )
    return info


ACCEPTABLE = re.compile(r"^(CC0|Public domain|CC BY(-SA|-NC|-NC-SA)? [\d.]+)", re.IGNORECASE)


def download_file(url, dest):
    r = get(url)
    r.raise_for_status()
    dest.write_bytes(r.content)


def transcoded_mp3(url):
    """URL of Commons' own MP3 transcode of an audio file.

    upload.wikimedia.org throttles downloads of originals hard (429 with a
    ten-minute Retry-After), while the cached transcodes are served freely.
    """
    base, _, path = url.split("?")[0].partition("/wikipedia/commons/")
    name = path.rsplit("/", 1)[-1]
    return f"{base}/wikipedia/commons/transcoded/{path}/{name}.mp3"


def to_mono_mp3(src, dest):
    """Trim long silence at both ends, peak-normalise to -4 dB (MP3 encoding
    overshoots by a couple of dB, so this avoids clipping), write a small mono MP3.

    Trimming keeps 0.1 s of padding and only cuts below -50 dB, so quiet
    final consonants (the k in "book") survive.
    """
    trim = (
        "silenceremove=start_periods=1:start_threshold=-50dB"
        ":start_silence=0.1:detection=peak"
    )
    trimmed = f"{trim},areverse,{trim},areverse"
    probe = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(src), "-af", f"{trimmed},volumedetect",
         "-f", "null", "-"],
        check=True, capture_output=True, text=True,
    )
    peak = float(re.search(r"max_volume: (-?[\d.]+) dB", probe.stderr).group(1))
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y", "-i", str(src),
            "-af", f"{trimmed},volume={-4 - peak}dB",
            "-ac", "1", "-ar", "44100", "-b:a", "64k", str(dest),
        ],
        check=True,
    )


def download(limit):
    with PICKS.open(encoding="utf-8") as f:
        picks = [p for p in csv.DictReader(f) if complete(p)][:limit]

    # Files already downloaded with a provenance row are kept as they are.
    have = {}
    if SOURCES.exists():
        with SOURCES.open(encoding="utf-8") as f:
            have = {s["file"]: s for s in csv.DictReader(f) if (MEDIA / s["file"]).exists()}

    today = datetime.date.today().isoformat()
    audio_titles = {
        p[f"audio_{lang}_title"]
        for p in picks
        for lang in languages(p)
        if f"audio/{lang}/{p['id']}_{lang}.mp3" not in have
    }
    info = commons_info(audio_titles)

    (MEDIA / "images").mkdir(parents=True, exist_ok=True)
    for lang in LANGS:
        (MEDIA / "audio" / lang).mkdir(parents=True, exist_ok=True)
    CONCEPTS.mkdir(parents=True, exist_ok=True)

    sources, concepts = [], collections.defaultdict(list)
    for i, p in enumerate(picks, 1):
        cid = p["id"]
        image = MEDIA / "images" / f"{cid}.png"
        if "images/" + image.name in have:
            sources.append(have["images/" + image.name])
        else:
            download_file(ARASAAC_PNG.format(p["arasaac_id"]), image)
            sources.append(
                dict(
                    zip(
                        SOURCE_FIELDS,
                        ["images/" + image.name, "ARASAAC", ARASAAC_PAGE.format(p["arasaac_id"]),
                         ARASAAC_AUTHOR, *CC_BY_NC_SA, today, sha256(image)],
                    )
                )
            )
        row = {k: p.get(k, "") for k in ("id", *LANGS, "level")}
        row["image"] = image.name
        for lang in LANGS:
            if lang not in languages(p):
                row[lang] = row[f"audio_{lang}"] = ""
                continue
            dest = MEDIA / "audio" / lang / f"{cid}_{lang}.mp3"
            row[f"audio_{lang}"] = dest.name
            if f"audio/{lang}/{dest.name}" in have:
                sources.append(have[f"audio/{lang}/{dest.name}"])
                continue
            title = p[f"audio_{lang}_title"]
            url, page, author, licence, licence_url = info[title]
            if not ACCEPTABLE.match(licence):
                sys.exit(f"{cid}: {title} has licence {licence!r}, which we can't use")
            with tempfile.TemporaryDirectory() as tmp:
                raw = Path(tmp) / "original.mp3"
                download_file(transcoded_mp3(url), raw)
                to_mono_mp3(raw, dest)
            source = "Lingua Libre" if title.startswith("File:LL-") else "Wikimedia Commons"
            sources.append(
                dict(
                    zip(
                        SOURCE_FIELDS,
                        [f"audio/{lang}/{dest.name}", source, page, author, licence,
                         licence_url, today, sha256(dest)],
                    )
                )
            )
        concepts[p["topic"]].append(row)
        print(f"[{i}/{len(picks)}] {cid}", file=sys.stderr)

    for topic, rows in concepts.items():
        with (CONCEPTS / f"{topic}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CONCEPT_FIELDS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    # Keep provenance rows for media this script doesn't manage (e.g. the
    # shape recordings from fetch_shape_audio.py).
    written = {s["file"] for s in sources}
    sources += [s for f, s in have.items() if f not in written]
    with SOURCES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SOURCE_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(sources, key=lambda s: s["file"]))

    print(f"downloaded media for {len(picks)} concepts into {len(concepts)} topic tables")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=["pick", "download"])
    ap.add_argument("--limit", type=int, help="only handle the first N words")
    args = ap.parse_args()
    {"pick": pick, "download": download}[args.step](args.limit)


if __name__ == "__main__":
    main()
