"""Picture → word decks, built from data/concepts/*.csv and media/.

Each language gets its own deck tree, one subdeck per topic:
Svenska::Ord::<Swedish topic> and English::Words::<English topic>. A card
shows a picture and four words from the same topic; the back shows the word,
plays its recording and credits the picture and the speaker.

Also writes ATTRIBUTION.md from media/sources.csv.
"""

import csv
import html
import random
import re
import sys
from pathlib import Path

import genanki

ROOT = Path(__file__).resolve().parent.parent
CONCEPTS = ROOT / "data" / "concepts"
MEDIA = ROOT / "media"

# Model and deck IDs are fixed forever: changing one makes Anki treat the
# note type or deck as new. Add new topics with fresh IDs; never reuse one.
MODEL_ID = 1104416739

# topic -> {language: (subdeck name, deck ID)}
TOPICS = {
    "animals": {"sv": ("Djur", 1509161000), "en": ("Animals", 1945329914),
               "de": ("Tiere", 1719208145), "sw": ("Wanyama", 1172855551)},
    "body": {"sv": ("Kroppen", 2093531152), "en": ("Body", 1573961684),
            "de": ("Körper", 1975168587), "sw": ("Mwili", 2049668633)},
    "clothes": {"sv": ("Kläder", 1486385459), "en": ("Clothes", 1298982429),
               "de": ("Kleidung", 1258231894), "sw": ("Nguo", 1836690930)},
    "colors": {"sv": ("Färger", 2091834092), "en": ("Colours", 1176715808),
              "de": ("Farben", 1320323415), "sw": ("Rangi", 1365366431)},
    "food": {"sv": ("Mat", 1883932933), "en": ("Food", 1786296919),
            "de": ("Essen", 1509077666), "sw": ("Chakula", 1473947504)},
    "home": {"sv": ("Hemma", 1612793067), "en": ("Home", 1162162490),
            "de": ("Zuhause", 1145172546), "sw": ("Nyumbani", 1889390712)},
    "nature": {"sv": ("Naturen", 1625126323), "en": ("Nature", 1305707322),
              "de": ("Natur", 1713924011), "sw": ("Maumbile", 1229174103)},
    "people": {"sv": ("Människor", 1704314440), "en": ("People", 1280040928),
              "de": ("Menschen", 1236117708), "sw": ("Watu", 2075743728)},
    "places": {"sv": ("Platser", 2033439675), "en": ("Places", 1134089514),
              "de": ("Orte", 1756371340), "sw": ("Mahali", 1290079648)},
    "toys": {"sv": ("Leksaker", 1523246323), "en": ("Toys", 1642344530),
            "de": ("Spielzeug", 1481293229), "sw": ("Vitu vya kuchezea", 1254962600)},
    "vehicles": {"sv": ("Fordon", 1914877154), "en": ("Vehicles", 1469005880),
                "de": ("Fahrzeuge", 1881566209), "sw": ("Vyombo vya usafiri", 2090973461)},
    "music": {"sv": ("Musik", 1752141239), "en": ("Music", 1727409939),
             "de": ("Musik", 1962259706), "sw": ("Muziki", 1281236435)},
    "sports": {"sv": ("Sport", 1803354422), "en": ("Sports", 1926662181),
              "de": ("Sport", 1329269040), "sw": ("Michezo", 1988179553)},
    "school": {"sv": ("Skolan", 1278447885), "en": ("School", 1314221429),
              "de": ("Schule", 1845751466), "sw": ("Shule", 1133622645)},
}
ACCEPTABLE = re.compile(
    r"^(CC0|Public domain|CC BY(-SA|-NC|-NC-SA)? [\d.]+)", re.IGNORECASE
)
LICENCE_NOTE = "Released under CC BY-NC-SA 4.0: https://github.com/nordmarj/Kids_Flashcards"

# Every language the decks are built in. To add one: add its entry here, its
# names to TOPICS, and a column with its code (and audio_<code>) to
# data/candidates/media_picks.csv (fetch_media.py download then adds them to
# the concept tables). For shape cards too, add a column to
# data/shapes/shapes.csv and an entry to build_decks.SHAPES_DECKS.
LANGUAGES = {
    "sv": {
        "root": "Svenska::Ord",
        "package": "svenska.apkg",
        "picture": "Bild",
        "sound": "Ljud",
        "description": "Kids Flashcards: titta på bilden och tryck på rätt ord. Bilder: "
        "ARASAAC (Sergio Palao, Aragoniens regering), CC BY-NC-SA. Ljud: Lingua Libre "
        "och Wikimedia Commons, se varje kort. " + LICENCE_NOTE,
    },
    "en": {
        "root": "English::Words",
        "package": "english.apkg",
        "picture": "Picture",
        "sound": "Sound",
        "description": "Kids Flashcards: look at the picture and tap the right word. "
        "Pictures: ARASAAC (Sergio Palao, Government of Aragón), CC BY-NC-SA. Sounds: "
        "Lingua Libre and Wikimedia Commons, see each card. " + LICENCE_NOTE,
    },
    "de": {
        "root": "Deutsch::Wörter",
        "package": "deutsch.apkg",
        "picture": "Bild",
        "sound": "Ton",
        "description": "Kids Flashcards: schau das Bild an und tippe auf das richtige Wort. "
        "Bilder: ARASAAC (Sergio Palao, Regierung von Aragonien), CC BY-NC-SA. Ton: "
        "Lingua Libre und Wikimedia Commons, siehe jede Karte. " + LICENCE_NOTE,
    },
    "sw": {
        "root": "Kiswahili::Maneno",
        "package": "kiswahili.apkg",
        "picture": "Picha",
        "sound": "Sauti",
        "description": "Kids Flashcards: tazama picha na ubonyeze neno sahihi. Picha: "
        "ARASAAC (Sergio Palao, Serikali ya Aragon), CC BY-NC-SA. Sauti: Wikimedia "
        "Commons, angalia kila kadi. " + LICENCE_NOTE,
    },
}


def read_sources():
    with (MEDIA / "sources.csv").open(encoding="utf-8", newline="") as f:
        sources = {row["file"]: row for row in csv.DictReader(f)}
    for row in sources.values():
        if not ACCEPTABLE.match(row["licence"]):
            sys.exit(f"media/{row['file']}: licence {row['licence']!r} is not acceptable")
        if not row["author"]:
            sys.exit(f"media/{row['file']}: no author in media/sources.csv, which attribution needs")
    on_disk = {p.relative_to(MEDIA).as_posix() for p in MEDIA.rglob("*")
               if p.is_file() and p.name != "sources.csv"}
    if on_disk - sources.keys():
        sys.exit(f"media files without a row in media/sources.csv: {sorted(on_disk - sources.keys())}")
    return sources


def media_file(sources, rel):
    """Path of a media file that exists and has a provenance row."""
    if rel not in sources:
        sys.exit(f"media/{rel} has no row in media/sources.csv")
    path = MEDIA / rel
    if not path.exists():
        sys.exit(f"media/{rel} is listed in media/sources.csv but missing")
    return path


def credit(row):
    """Author and licence for a card; public domain files have no licence URL."""
    licence = html.escape(row["licence"])
    if row["licence_url"]:
        licence = f'<a href="{html.escape(row["licence_url"])}">{licence}</a>'
    return f'{html.escape(row["author"])}, {licence}'


def read_concepts():
    topics = {}
    for path in sorted(CONCEPTS.glob("*.csv")):
        if path.stem not in TOPICS:
            sys.exit(f"{path.relative_to(ROOT)}: topic has no deck names/IDs in word_decks.TOPICS")
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        for line, row in enumerate(rows, start=2):
            # A concept may exist in only some languages, but a language it
            # has needs both the word and its recording.
            where = f"{path.relative_to(ROOT)}:{line}"
            missing = [k for k in ("id", "level", "image") if not row.get(k)]
            if missing:
                sys.exit(f"{where}: empty {', '.join(missing)}")
            for lang in LANGUAGES:
                if bool(row.get(lang)) != bool(row.get(f"audio_{lang}")):
                    sys.exit(f"{where}: {lang} needs both the word and audio_{lang}, or neither")
            if not any(row.get(lang) for lang in LANGUAGES):
                sys.exit(f"{where}: no language has a word")
        topics[path.stem] = rows
    return topics


def model(choices_js):
    tpl = ROOT / "templates" / "picture_choice"
    label = (tpl / "language_label.html").read_text(encoding="utf-8")
    read = lambda name: ((tpl / name).read_text(encoding="utf-8")
                         .replace("{{CHOICES_JS}}", choices_js)
                         .replace("{{LANGUAGE_LABEL}}", label))
    return genanki.Model(
        MODEL_ID,
        "Kids Flashcards: Picture to word",
        fields=[{"name": "Word"}, {"name": "Picture"}, {"name": "Audio"},
                {"name": "Choices"}, {"name": "Credits"}],
        templates=[{
            "name": "Picture to word",
            "qfmt": read("front.html"),
            "afmt": read("back.html"),
        }],
        css=(tpl / "style.css").read_text(encoding="utf-8"),
    )


def distractors(concept, rows, lang):
    """Three other words from the same topic, picked stably per concept."""
    pool = [r for r in rows if r["id"] != concept["id"] and r[lang] != concept[lang]]
    return random.Random(f"words:{concept['id']}:{lang}").sample(pool, 3)


def build(langs=tuple(LANGUAGES)):
    """Return {language: (decks, media files)} for the given languages."""
    sources = read_sources()
    topics = read_concepts()
    choices_js = (ROOT / "templates" / "shapes" / "choices_script.html").read_text(encoding="utf-8")
    note_model = model(choices_js)
    button = '<button type="button" class="choice"{ok}>{word}</button>'

    out = {}
    for lang in langs:
        decks, files = [], set()
        for topic, all_rows in topics.items():
            rows = [r for r in all_rows if r.get(lang)]
            if not rows:
                continue
            # A card needs three wrong choices; a topic too small to supply
            # them borrows words from the language's other topics.
            pool = rows if len(rows) >= 4 else rows + [
                r for t, other in topics.items() if t != topic for r in other if r.get(lang)]
            name, deck_id = TOPICS[topic][lang]
            info = LANGUAGES[lang]
            deck = genanki.Deck(deck_id, f"{info['root']}::{name}", description=info["description"])
            for due, c in enumerate(rows):
                image = media_file(sources, f"images/{c['image']}")
                audio = media_file(sources, f"audio/{lang}/{c[f'audio_{lang}']}")
                files.update([image, audio])
                options = [c] + distractors(c, pool, lang)
                choices = "".join(
                    button.format(ok=' data-ok="1"' if o is c else "", word=html.escape(o[lang]))
                    for o in options
                )
                credits = (f"{info['picture']}: {credit(sources[f'images/{image.name}'])} · "
                           f"{info['sound']}: {credit(sources[f'audio/{lang}/{audio.name}'])}")
                deck.add_note(genanki.Note(
                    model=note_model,
                    fields=[html.escape(c[lang]), f'<img src="{image.name}">',
                            f"[sound:{audio.name}]", choices, credits],
                    guid=genanki.guid_for("kids_flashcards", "words", c["id"], lang),
                    tags=[f"level{c['level']}", topic, f"lang_{lang}"],
                    due=due,
                ))
            decks.append(deck)
        out[lang] = (decks, sorted(files))
        print(f"{sum(len(d.notes) for d in decks)} {lang} word cards in {len(decks)} topic subdecks")
    write_attribution(sources)
    return out


def write_attribution(sources):
    lines = [
        "# Attribution",
        "",
        "Generated by `scripts/build_decks.py` from `media/sources.csv`; do not edit by hand.",
        "",
        "Pictographic symbols are the property of the Government of Aragón and were "
        "created by Sergio Palao for [ARASAAC](https://arasaac.org), licensed under "
        "[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).",
        "",
        "Recordings come from [Lingua Libre](https://lingualibre.org) and "
        "[Wikimedia Commons](https://commons.wikimedia.org), each under its own licence:",
        "",
        "| File | Source | Author | Licence |",
        "|------|--------|--------|---------|",
    ]
    for row in sorted(sources.values(), key=lambda r: r["file"]):
        if row["source"] == "ARASAAC":
            continue
        author = row["author"].replace("|", "\\|")
        licence = (f"[{row['licence']}]({row['licence_url']})" if row["licence_url"]
                   else row["licence"])
        lines.append(f"| {row['file']} | [{row['source']}]({row['source_url']}) | {author} | "
                     f"{licence} |")
    (ROOT / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
