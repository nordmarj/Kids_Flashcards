#!/usr/bin/env python3
"""Pick and download the flags, maps and recorded names for the geography deck.

Two steps, like fetch_media.py, so the choices can be reviewed (and edited by
hand) before anything is downloaded:

  pick      Find every ARASAAC flag and map pictogram of a country, region or
            continent, group them into one row per place, look its name up in
            each language on Wikidata (plus ARASAAC's own keywords), and match
            the names to recordings on Wikimedia Commons. Writes
            data/candidates/geography_picks.csv. Places already in that file
            are kept as they are, so hand edits survive: to fix a wrong
            Wikidata item, put the right one in its `wikidata` column and blank
            every recording title, and the place is looked up again; blank one
            recording title (and its name) to drop that language.
  download  Download everything in geography_picks.csv that isn't in media/
            yet, record provenance in media/sources.csv and write
            data/geography/<topic>.csv.

A place is only kept when at least one language has a recording of its name;
the other languages are left empty and the place appears only in the decks of
the languages it has.

`pick` matches recordings against a list of Commons file titles instead of
searching Commons word by word (the search API throttles hard). Make the list
from the title dump, which takes a few minutes:

  curl -sA "<your user agent>" \\
    https://dumps.wikimedia.org/commonswiki/latest/commonswiki-latest-all-titles.gz \\
    | zcat | grep -E '^6\t(LL-Q|Sv-|En-|De-|Es-|Fr-|Sw-)' > titles.txt

Usage: python3 scripts/fetch_geography.py pick --titles titles.txt
       python3 scripts/fetch_geography.py download
"""

import argparse
import collections
import csv
import datetime
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_coverage import LINGUA_LIBRE, get  # noqa: E402
from fetch_media import (  # noqa: E402
    ACCEPTABLE,
    ARASAAC_AUTHOR,
    ARASAAC_PAGE,
    ARASAAC_PNG,
    CC_BY_NC_SA,
    MEDIA,
    SOURCE_FIELDS,
    SOURCES,
    commons_info,
    download_file,
    sha256,
    to_mono_mp3,
    transcoded_mp3,
    write_sources,
)
from word_decks import LANGUAGES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PICKS = ROOT / "data" / "candidates" / "geography_picks.csv"
GEOGRAPHY = ROOT / "data" / "geography"

ARASAAC_ALL = "https://api.arasaac.org/v1/pictograms/all/{}"
SPARQL = "https://query.wikidata.org/sparql"

LANGS = list(LANGUAGES)
PICK_FIELDS = (["id", "topic", *LANGS, "level", "wikidata", "flag_arasaac_id", "map_arasaac_id"]
               + [f"audio_{lang}_title" for lang in LANGS])
TABLE_FIELDS = ["id", *LANGS, "level", "flag", "map"] + [f"audio_{lang}" for lang in LANGS]

# Pictograms in the flag/country/continent categories that don't show a place.
NOT_PLACES = {
    5918, 5919,  # flag, pennant
    12338,  # nationality
    28489,  # to hoist
    30023,  # embassy
    34547,  # continents
    35431,  # country
    36981,  # Wiphala, the Andean peoples' flag
    10476,  # a second map of Spain (28967 is kept)
    27304,  # Martinique's snake flag, no longer its flag since 2023
}

# Place ids for pictograms whose first English keyword is not the slug we want,
# so that a country's flag and map land in the same row.
PLACE_IDS = {
    "holland": "netherlands",
    "the_netherlands": "netherlands",
    "surinam": "suriname",
    "united_states_of_america": "united_states",
    "america": "americas",
    "turkiye": "turkey",
    "burma": "myanmar",
    "tadzhikistan": "tajikistan",
    "faeroe_islands": "faroe_islands",
    "french_guyana": "french_guiana",
    "andalusia_andalucia": "andalusia",
    "castille_la_mancha": "castilla_la_mancha",
    "castile_leon": "castile_and_leon",
    "madrid_region": "community_of_madrid",
    "valencia_region": "valencian_community",
}
# The flag of Europe (8117) belongs with the map of the continent.
FLAG_OF = {8117: "europe"}

CONTINENTS = {"africa", "americas", "asia", "europe", "oceania", "antarctica"}
SPAIN = "spain region"

# Places a young child is most likely to know: the Nordic countries, the
# largest neighbours and the countries that are often in children's books.
# Everything else is level 2.
LEVEL1 = {
    "sweden", "norway", "denmark", "finland", "iceland", "germany", "france",
    "spain", "italy", "united_kingdom", "united_states", "canada", "mexico",
    "brazil", "china", "japan", "india", "russia", "australia", "egypt",
    "kenya", "tanzania", "south_africa", *CONTINENTS,
}

# Articles a recording may include (German "die Schweiz", French "la France").
ARTICLES = {
    "de": ["die ", "der ", "das "],
    "fr": ["la ", "le ", "les ", "l'", "l’"],
    "es": ["el ", "la ", "los ", "las "],
    "sv": [], "en": ["the "], "sw": [],
}


def slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def fold(text):
    """Key for matching a name to a recording's file name."""
    return unicodedata.normalize("NFC", text).replace("_", " ").replace("’", "'").casefold().strip()


# ---------------------------------------------------------------- pick


def arasaac_places():
    """{place id: {"topic", "flag", "map", "keywords": {lang: [names]}}}."""
    pictos = {}
    for lang in ("en", "sv", "de", "es", "fr"):
        r = get(ARASAAC_ALL.format(lang))
        r.raise_for_status()
        for p in r.json():
            pictos.setdefault(p["_id"], {})[lang] = p
    places = {}
    for pid, by_lang in sorted(pictos.items()):
        en = by_lang["en"]
        cats = set(en.get("categories", []))
        if not cats & {"flag", "country", "continent"} or pid in NOT_PLACES:
            continue
        if en.get("sex") or en.get("violence") or not en.get("keywords"):
            continue
        kind = "flag" if "flag" in cats else "map"
        first = en["keywords"][0]["keyword"].split("/")[0]
        place = FLAG_OF.get(pid) or PLACE_IDS.get(slug(first), slug(first))
        if place in CONTINENTS:
            topic = "continents"
        elif SPAIN in cats or "city" in cats:
            topic = "regions"
        else:
            topic = "countries"
        entry = places.setdefault(
            place, {"topic": topic, "flag": "", "map": "", "keywords": collections.defaultdict(list)}
        )
        if place in CONTINENTS:
            entry["topic"] = "continents"
        if entry[kind]:
            print(f"  {place}: second {kind} pictogram {pid} ignored "
                  f"(keeping {entry[kind]})", file=sys.stderr)
            continue
        entry[kind] = str(pid)
        if FLAG_OF.get(pid):
            continue  # the flag of Europe isn't named "Europe" in every language
        for lang, p in by_lang.items():
            for k in p.get("keywords", []):
                for name in k["keyword"].split("/"):
                    if name.strip():
                        entry["keywords"][lang].append(name.strip())
    return places


def sparql(query):
    r = get(SPARQL, query=query, format="json")
    r.raise_for_status()
    return r.json()["results"]["bindings"]


def wikidata_items(names):
    """{English name: Wikidata item} for place names.

    Uses the query service rather than the Wikidata API, which throttles
    hard. Among items with that English label or alias, a country (it has
    an ISO 3166-1 code) or a continent wins, then a region (ISO 3166-2
    code), then the item with most Wikipedia articles.
    """
    best = {}
    names = sorted(set(names))
    for start in range(0, len(names), 40):
        values = " ".join('"{}"@en'.format(n.replace('"', '\\"')) for n in names[start:start + 40])
        rows = sparql(f"""
            SELECT ?name ?item ?links ?iso ?sub ?continent WHERE {{
              VALUES ?name {{ {values} }}
              ?item rdfs:label|skos:altLabel ?name; wikibase:sitelinks ?links .
              OPTIONAL {{ ?item wdt:P297 ?iso }}
              OPTIONAL {{ ?item wdt:P300 ?sub }}
              OPTIONAL {{ ?item wdt:P31 ?continent FILTER(?continent = wd:Q5107) }}
            }}""")
        for row in rows:
            name = row["name"]["value"]
            score = (2 if "iso" in row or "continent" in row else 1 if "sub" in row else 0,
                     int(row["links"]["value"]))
            item = row["item"]["value"].rsplit("/", 1)[-1]
            if name not in best or score > best[name][0]:
                best[name] = (score, item)
    return {name: item for name, (_, item) in best.items()}


def wikidata_names(items):
    """{item: {lang: ([label], [aliases])}}.

    Short all-capital aliases are codes ("SE", "UK"), which could match a
    recording of an ordinary word ("se"), so they are left out.
    """
    names = {i: {lang: ([], []) for lang in LANGS} for i in items if i}
    items = sorted(names)
    langs = ", ".join(f'"{lang}"' for lang in LANGS)
    for start in range(0, len(items), 100):
        values = " ".join(f"wd:{i}" for i in items[start:start + 100])
        rows = sparql(f"""
            SELECT ?item ?label ?alias WHERE {{
              VALUES ?item {{ {values} }}
              {{ ?item rdfs:label ?label FILTER(LANG(?label) IN ({langs})) }}
              UNION
              {{ ?item skos:altLabel ?alias FILTER(LANG(?alias) IN ({langs})) }}
            }}""")
        for row in rows:
            item = row["item"]["value"].rsplit("/", 1)[-1]
            if "label" in row:
                names[item][row["label"]["xml:lang"]][0].append(row["label"]["value"])
            else:
                alias = row["alias"]["value"]
                if not (alias.isupper() and len(alias) <= 3):
                    names[item][row["alias"]["xml:lang"]][1].append(alias)
    return names


def recording_index(titles_path):
    """{lang: {folded word: [(speaker, title)]}} from a Commons title list."""
    patterns = []
    for lang, prefix in LINGUA_LIBRE.items():
        # The speaker part may not contain a hyphen, as in fetch_media.py.
        patterns.append((lang, re.compile(rf"^{re.escape(prefix)}-([^-]+)-(.+)\.(wav|ogg|flac|mp3)$")))
    fallback = {"sv": ["Sv"], "en": ["En-us", "En-uk", "En-au"], "de": ["De"],
                "sw": ["Sw-ke"], "es": ["Es"], "fr": ["Fr"]}
    for lang, prefixes in fallback.items():
        for prefix in prefixes:
            patterns.append((lang, re.compile(rf"^({re.escape(prefix)})-(.+)\.(ogg|flac|wav|mp3)$")))
    index = {lang: collections.defaultdict(list) for lang in LANGS}
    with open(titles_path, encoding="utf-8") as f:
        for line in f:
            title = line.rstrip("\n").split("\t")[-1].replace("_", " ")
            for lang, pattern in patterns:
                m = pattern.match(title)
                if m:
                    index[lang][fold(m.group(2))].append((m.group(1), "File:" + title))
                    break
    return index


def candidates(lang, names):
    """Names to try, in order, each also with the articles a recording may include."""
    out = []
    for name in names:
        for article in ["", *ARTICLES[lang]]:
            if (article + name) not in out:
                out.append(article + name)
    return out


def pick(titles_path):
    kept = []
    if PICKS.exists():
        with PICKS.open(encoding="utf-8") as f:
            kept = list(csv.DictReader(f))
    known = {p["id"]: p for p in kept}

    places = arasaac_places()
    index = recording_index(titles_path)

    # Wikidata item per place; earlier (possibly hand-fixed) items are kept.
    found_items = wikidata_items(e["keywords"]["en"][0] for e in places.values())
    items = {place: known.get(place, {}).get("wikidata")
             or found_items.get(entry["keywords"]["en"][0], "")
             for place, entry in places.items()}
    wd = wikidata_names(items.values())

    # Every recording that matches some place's name, per language, so the
    # speaker with the most of them can be preferred (one voice per deck).
    found = {}
    rank = {lang: collections.Counter() for lang in LANGS}
    for place, entry in places.items():
        for lang in LANGS:
            # Wikidata's label first, then ARASAAC's keyword, then other names.
            label, aliases = wd.get(items[place], {}).get(lang, ([], []))
            names = label + entry["keywords"].get(lang, []) + aliases
            hits = [(name, rec) for name in candidates(lang, names) for rec in index[lang].get(fold(name), [])]
            found[place, lang] = hits
            rank[lang].update({speaker for _, (speaker, _) in hits})

    picks = []
    for place, entry in sorted(places.items()):
        if any(known.get(place, {}).get(f"audio_{lang}_title") for lang in LANGS):
            p = dict(known[place])
            p["flag_arasaac_id"] = p.get("flag_arasaac_id") or entry["flag"]
            p["map_arasaac_id"] = p.get("map_arasaac_id") or entry["map"]
            picks.append(p)
            continue
        p = {"id": place, "topic": entry["topic"], "level": 1 if place in LEVEL1 else 2,
             "wikidata": items[place], "flag_arasaac_id": entry["flag"],
             "map_arasaac_id": entry["map"]}
        for lang in LANGS:
            hits = found[place, lang]
            p[lang] = p[f"audio_{lang}_title"] = ""
            if hits:
                # The first name with a recording wins; among its recordings,
                # the most prolific speaker's.
                name = hits[0][0]
                speaker, title = max((r for n, r in hits if n == name), key=lambda r: rank[lang][r[0]])
                if not any(name.startswith(a) for a in ARTICLES[lang]):
                    name = name[0].upper() + name[1:]  # "pays de Galles" starts a card
                p[lang], p[f"audio_{lang}_title"] = name, title
        picks.append(p)

    picks = [p for p in picks if any(p[f"audio_{lang}_title"] for lang in LANGS)]
    PICKS.parent.mkdir(parents=True, exist_ok=True)
    with PICKS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PICK_FIELDS, restval="", lineterminator="\n")
        w.writeheader()
        w.writerows(picks)

    left_out = sorted(set(places) - {p["id"] for p in picks})
    print(f"wrote {len(picks)} places to {PICKS.relative_to(ROOT)}")
    for lang in LANGS:
        print(f"  {lang}: {sum(1 for p in picks if p[f'audio_{lang}_title'])} recorded names")
    if left_out:
        print("no recording in any language (left out): " + ", ".join(left_out))


# ---------------------------------------------------------------- download


def download(limit):
    with PICKS.open(encoding="utf-8") as f:
        picks = [p for p in csv.DictReader(f)][:limit]

    have = {}
    if SOURCES.exists():
        with SOURCES.open(encoding="utf-8") as f:
            have = {s["file"]: s for s in csv.DictReader(f) if (MEDIA / s["file"]).exists()}

    today = datetime.date.today().isoformat()
    audio_titles = {
        p[f"audio_{lang}_title"]
        for p in picks
        for lang in LANGS
        if p[f"audio_{lang}_title"] and f"audio/{lang}/geo_{p['id']}_{lang}.mp3" not in have
    }
    info = commons_info(audio_titles)

    sources, tables, failed = [], collections.defaultdict(list), []
    for lang in LANGS:
        (MEDIA / "audio" / lang).mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(picks, 1):
        pid = p["id"]
        row = {k: p[k] for k in ("id", *LANGS, "level")}
        for kind in ("flag", "map"):
            row[kind] = ""
            arasaac_id = p[f"{kind}_arasaac_id"]
            if not arasaac_id:
                continue
            image = MEDIA / "images" / f"{kind}_{pid}.png"
            if "images/" + image.name in have:
                sources.append(have["images/" + image.name])
            else:
                try:
                    download_file(ARASAAC_PNG.format(arasaac_id), image)
                except requests.RequestException as e:
                    print(f"  {pid}: {kind} not downloaded ({e}); rerun to retry", file=sys.stderr)
                    failed.append(f"{kind}_{pid}")
                    image.unlink(missing_ok=True)
                    continue
                sources.append(dict(zip(SOURCE_FIELDS, [
                    "images/" + image.name, "ARASAAC", ARASAAC_PAGE.format(arasaac_id),
                    ARASAAC_AUTHOR, *CC_BY_NC_SA, today, sha256(image)])))
            row[kind] = image.name
        for lang in LANGS:
            title = p[f"audio_{lang}_title"]
            row[f"audio_{lang}"] = ""
            if not (p[lang] and title):
                row[lang] = ""
                continue
            dest = MEDIA / "audio" / lang / f"geo_{pid}_{lang}.mp3"
            if f"audio/{lang}/{dest.name}" in have:
                sources.append(have[f"audio/{lang}/{dest.name}"])
                row[f"audio_{lang}"] = dest.name
                continue
            if title not in info or not ACCEPTABLE.match(info[title][3] or ""):
                print(f"  {pid}: {lang} recording {title} not usable, left out", file=sys.stderr)
                row[lang] = ""
                continue
            url, page, author, licence, licence_url = info[title]
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    raw = Path(tmp) / "original.mp3"
                    download_file(transcoded_mp3(url), raw)
                    to_mono_mp3(raw, dest)
            except (requests.RequestException, subprocess.CalledProcessError) as e:
                print(f"  {pid}: {lang} recording not downloaded ({e}); rerun to retry",
                      file=sys.stderr)
                failed.append(f"{pid}_{lang}")
                row[lang] = ""
                continue
            source = "Lingua Libre" if title.startswith("File:LL-") else "Wikimedia Commons"
            sources.append(dict(zip(SOURCE_FIELDS, [
                f"audio/{lang}/{dest.name}", source, page, author, licence, licence_url,
                today, sha256(dest)])))
            row[f"audio_{lang}"] = dest.name
        if (row["flag"] or row["map"]) and any(row[f"audio_{lang}"] for lang in LANGS):
            tables[p["topic"]].append(row)
        print(f"[{i}/{len(picks)}] {pid}", file=sys.stderr)
        if i % 25 == 0:
            write_sources(sources, have)

    GEOGRAPHY.mkdir(parents=True, exist_ok=True)
    for topic, rows in tables.items():
        with (GEOGRAPHY / f"{topic}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TABLE_FIELDS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    write_sources(sources, have)

    print(f"wrote {sum(len(r) for r in tables.values())} places into {len(tables)} tables")
    if failed:
        print(f"{len(failed)} files not downloaded yet (rerun to retry): " + ", ".join(failed))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=["pick", "download"])
    ap.add_argument("--titles", help="Commons file titles to match recordings against (pick)")
    ap.add_argument("--limit", type=int, help="only download the first N places")
    args = ap.parse_args()
    if args.step == "pick":
        if not args.titles:
            ap.error("pick needs --titles")
        pick(args.titles)
    else:
        download(args.limit)


if __name__ == "__main__":
    main()
