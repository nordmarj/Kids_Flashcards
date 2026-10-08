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
    "animals": {"sv": ("Djur", 1509161000), "en": ("Animals", 1945329914)},
    "body": {"sv": ("Kroppen", 2093531152), "en": ("Body", 1573961684)},
    "clothes": {"sv": ("Kläder", 1486385459), "en": ("Clothes", 1298982429)},
    "colors": {"sv": ("Färger", 2091834092), "en": ("Colours", 1176715808)},
    "food": {"sv": ("Mat", 1883932933), "en": ("Food", 1786296919)},
    "home": {"sv": ("Hemma", 1612793067), "en": ("Home", 1162162490)},
    "nature": {"sv": ("Naturen", 1625126323), "en": ("Nature", 1305707322)},
    "people": {"sv": ("Människor", 1704314440), "en": ("People", 1280040928)},
    "places": {"sv": ("Platser", 2033439675), "en": ("Places", 1134089514)},
    "toys": {"sv": ("Leksaker", 1523246323), "en": ("Toys", 1642344530)},
    "vehicles": {"sv": ("Fordon", 1914877154), "en": ("Vehicles", 1469005880)},
}
ACCEPTABLE = re.compile(
    r"^(CC0|Public domain|CC BY(-SA|-NC|-NC-SA)? [\d.]+)", re.IGNORECASE
)
LICENCE_NOTE = "Released under CC BY-NC-SA 4.0: https://github.com/nordmarj/Kids_Flashcards"

# Every language the decks are built in. To add one: add its entry here, a
# column with its code (and audio_<code>) to every concept table and to
# data/shapes/shapes.csv, and its names to TOPICS and build_decks.SHAPES_DECKS.
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
            needed = ["id", "image"] + [k for lang in LANGUAGES for k in (lang, f"audio_{lang}")]
            missing = [k for k in needed if not row.get(k)]
            if missing:
                sys.exit(f"{path.relative_to(ROOT)}:{line}: empty {', '.join(missing)}")
        topics[path.stem] = rows
    return topics


def model(choices_js):
    tpl = ROOT / "templates" / "picture_choice"
    read = lambda name: (tpl / name).read_text(encoding="utf-8").replace("{{CHOICES_JS}}", choices_js)
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
        for topic, rows in topics.items():
            name, deck_id = TOPICS[topic][lang]
            info = LANGUAGES[lang]
            deck = genanki.Deck(deck_id, f"{info['root']}::{name}", description=info["description"])
            for due, c in enumerate(rows):
                image = media_file(sources, f"images/{c['image']}")
                audio = media_file(sources, f"audio/{lang}/{c[f'audio_{lang}']}")
                files.update([image, audio])
                options = [c] + distractors(c, rows, lang)
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
                    tags=[f"level{c['level']}", topic],
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
