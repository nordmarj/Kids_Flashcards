"""Word decks, built from data/concepts/*.csv and media/.

Each language gets its own deck tree, one subdeck per topic:
Svenska::Ord::<Swedish topic> and English::Words::<English topic>. Every
word has two multiple-choice cards in its topic subdeck. "Picture to word"
shows a picture and four words from the same topic; the back shows the word,
plays its recording and credits the picture and the speaker. "Word to
picture" shows the word, plays its recording and offers four pictures from
the same topic; the back shows the word and its picture.

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
# Word to picture is its own note type, so adding it left the picture to word
# note type, and the progress on its cards, untouched.
WORD_TO_PICTURE_MODEL_ID = 1630271958

# topic -> {language: (subdeck name, deck ID)}
TOPICS = {
    "animals": {"sv": ("Djur", 1509161000), "en": ("Animals", 1945329914),
               "de": ("Tiere", 1719208145), "sw": ("Wanyama", 1172855551),
               "es": ("Animales", 1248833739), "fr": ("Animaux", 1836922197)},
    "body": {"sv": ("Kroppen", 2093531152), "en": ("Body", 1573961684),
            "de": ("Körper", 1975168587), "sw": ("Mwili", 2049668633),
            "es": ("Cuerpo", 1495289796), "fr": ("Corps", 1865673697)},
    "clothes": {"sv": ("Kläder", 1486385459), "en": ("Clothes", 1298982429),
               "de": ("Kleidung", 1258231894), "sw": ("Nguo", 1836690930),
               "es": ("Ropa", 1861582769), "fr": ("Vêtements", 1240375460)},
    "colors": {"sv": ("Färger", 2091834092), "en": ("Colours", 1176715808),
              "de": ("Farben", 1320323415), "sw": ("Rangi", 1365366431),
              "es": ("Colores", 1142606839), "fr": ("Couleurs", 1717380853)},
    "food": {"sv": ("Mat", 1883932933), "en": ("Food", 1786296919),
            "de": ("Essen", 1509077666), "sw": ("Chakula", 1473947504),
            "es": ("Comida", 1587086199), "fr": ("Nourriture", 1637456672)},
    "home": {"sv": ("Hemma", 1612793067), "en": ("Home", 1162162490),
            "de": ("Zuhause", 1145172546), "sw": ("Nyumbani", 1889390712),
            "es": ("Casa", 1365657408), "fr": ("Maison", 1773874960)},
    "nature": {"sv": ("Naturen", 1625126323), "en": ("Nature", 1305707322),
              "de": ("Natur", 1713924011), "sw": ("Maumbile", 1229174103),
              "es": ("Naturaleza", 2003034850), "fr": ("Nature", 1929974124)},
    "people": {"sv": ("Människor", 1704314440), "en": ("People", 1280040928),
              "de": ("Menschen", 1236117708), "sw": ("Watu", 2075743728),
              "es": ("Personas", 1319427944), "fr": ("Personnes", 1390050761)},
    "places": {"sv": ("Platser", 2033439675), "en": ("Places", 1134089514),
              "de": ("Orte", 1756371340), "sw": ("Mahali", 1290079648),
              "es": ("Lugares", 2061261623), "fr": ("Lieux", 1546203241)},
    "toys": {"sv": ("Leksaker", 1523246323), "en": ("Toys", 1642344530),
            "de": ("Spielzeug", 1481293229), "sw": ("Vitu vya kuchezea", 1254962600),
            "es": ("Juguetes", 1469523877), "fr": ("Jouets", 2098447489)},
    "vehicles": {"sv": ("Fordon", 1914877154), "en": ("Vehicles", 1469005880),
                "de": ("Fahrzeuge", 1881566209), "sw": ("Vyombo vya usafiri", 2090973461),
                "es": ("Vehículos", 1806986258), "fr": ("Véhicules", 1999060444)},
    "music": {"sv": ("Musik", 1752141239), "en": ("Music", 1727409939),
             "de": ("Musik", 1962259706), "sw": ("Muziki", 1281236435),
             "es": ("Música", 1551968577), "fr": ("Musique", 2009481959)},
    "sports": {"sv": ("Sport", 1803354422), "en": ("Sports", 1926662181),
              "de": ("Sport", 1329269040), "sw": ("Michezo", 1988179553),
              "es": ("Deportes", 1776965400), "fr": ("Sports", 1888241247)},
    "school": {"sv": ("Skolan", 1278447885), "en": ("School", 1314221429),
              "de": ("Schule", 1845751466), "sw": ("Shule", 1133622645),
              "es": ("Escuela", 1809440249), "fr": ("École", 1753630662)},
}
ACCEPTABLE = re.compile(
    r"^(CC0|Public domain|CC BY(-SA|-NC|-NC-SA)? [\d.]+)", re.IGNORECASE
)
LICENCE_NOTE = "Released under CC BY-NC-SA 4.0: https://github.com/nordmarj/Kids_Flashcards"

# Every language the decks are built in. To add one: add its entry here, its
# names to TOPICS, and a column with its code (and audio_<code>) to
# data/candidates/media_picks.csv (fetch_media.py download then adds them to
# the concept tables). It also needs a column (and audio_<code>) in
# data/shapes/shapes.csv and an entry in build_decks.SHAPES_DECKS.
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
    "es": {
        "root": "Español::Palabras",
        "package": "espanol.apkg",
        "picture": "Imagen",
        "sound": "Sonido",
        "description": "Kids Flashcards: mira la imagen y toca la palabra correcta. "
        "Imágenes: ARASAAC (Sergio Palao, Gobierno de Aragón), CC BY-NC-SA. Sonido: "
        "Lingua Libre y Wikimedia Commons, ver cada tarjeta. " + LICENCE_NOTE,
    },
    "fr": {
        "root": "Français::Mots",
        "package": "francais.apkg",
        "picture": "Image",
        "sound": "Son",
        "description": "Kids Flashcards : regarde l'image et touche le bon mot. "
        "Images : ARASAAC (Sergio Palao, Gouvernement d'Aragon), CC BY-NC-SA. Son : "
        "Lingua Libre et Wikimedia Commons, voir chaque carte. " + LICENCE_NOTE,
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


def models(choices_js):
    """The picture to word and the word to picture note types."""
    tpl = ROOT / "templates" / "picture_choice"
    label = (tpl / "language_label.html").read_text(encoding="utf-8")
    read = lambda name: ((tpl / name).read_text(encoding="utf-8")
                         .replace("{{CHOICES_JS}}", choices_js)
                         .replace("{{LANGUAGE_LABEL}}", label))
    css = (tpl / "style.css").read_text(encoding="utf-8")
    picture_to_word = genanki.Model(
        MODEL_ID,
        "Kids Flashcards: Picture to word",
        fields=[{"name": "Word"}, {"name": "Picture"}, {"name": "Audio"},
                {"name": "Choices"}, {"name": "Credits"}],
        templates=[{
            "name": "Picture to word",
            "qfmt": read("front.html"),
            "afmt": read("back.html"),
        }],
        css=css,
    )
    word_to_picture = genanki.Model(
        WORD_TO_PICTURE_MODEL_ID,
        "Kids Flashcards: Word to picture",
        fields=[{"name": "Word"}, {"name": "Picture"}, {"name": "Audio"},
                {"name": "PictureChoices"}, {"name": "Credits"}],
        templates=[{
            "name": "Word to picture",
            "qfmt": read("word_front.html"),
            "afmt": read("word_back.html"),
        }],
        css=css,
    )
    return picture_to_word, word_to_picture


def distractors(concept, rows, lang):
    """Three other words from the same topic, picked stably per concept.

    The word to picture card offers the same three, so none of them may share
    the concept's picture either.
    """
    pool = [r for r in rows if r["id"] != concept["id"] and r[lang] != concept[lang]
            and r["image"] != concept["image"]]
    return random.Random(f"words:{concept['id']}:{lang}").sample(pool, 3)


def build(langs=tuple(LANGUAGES)):
    """Return {language: (decks, media files)} for the given languages."""
    sources = read_sources()
    topics = read_concepts()
    choices_js = (ROOT / "templates" / "shapes" / "choices_script.html").read_text(encoding="utf-8")
    picture_to_word, word_to_picture = models(choices_js)
    button = '<button type="button" class="choice"{ok}>{content}</button>'

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
                options = [c] + distractors(c, pool, lang)
                images = [media_file(sources, f"images/{o['image']}") for o in options]
                audio = media_file(sources, f"audio/{lang}/{c[f'audio_{lang}']}")
                files.update([*images, audio])
                ok = lambda o: ' data-ok="1"' if o is c else ""
                words = "".join(button.format(ok=ok(o), content=html.escape(o[lang]))
                                for o in options)
                pictures = "".join(button.format(ok=ok(o), content=f'<img src="{i.name}">')
                                   for o, i in zip(options, images))
                credits = (f"{info['picture']}: {credit(sources[f'images/{images[0].name}'])} · "
                           f"{info['sound']}: {credit(sources[f'audio/{lang}/{audio.name}'])}")
                word, picture = html.escape(c[lang]), f'<img src="{images[0].name}">'
                tags = [f"level{c['level']}", topic, f"lang_{lang}"]
                deck.add_note(genanki.Note(
                    model=picture_to_word,
                    fields=[word, picture, f"[sound:{audio.name}]", words, credits],
                    guid=genanki.guid_for("kids_flashcards", "words", c["id"], lang),
                    tags=tags,
                    due=due,
                ))
                deck.add_note(genanki.Note(
                    model=word_to_picture,
                    fields=[word, picture, f"[sound:{audio.name}]", pictures, credits],
                    guid=genanki.guid_for("kids_flashcards", "word_to_picture", c["id"], lang),
                    tags=tags,
                    due=due,
                ))
            decks.append(deck)
        out[lang] = (decks, sorted(files))
        words = sum(len(d.notes) for d in decks) // 2
        print(f"{words} {lang} words ({2 * words} cards) in {len(decks)} topic subdecks")
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
