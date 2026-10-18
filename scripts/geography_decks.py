"""Geography decks: a flag or map → place name, built from data/geography/*.csv.

Each language gets its own package (build/geography_<lang>.apkg) with a
subdeck for flags and one for maps, e.g. Geografi::Flaggor and
Geografi::Kartor. A place is in a language's deck only when it has a
recorded name in that language, so each deck holds everything the
language has. Every flag and map gets two multiple-choice cards, like the
shapes: "Picture to name" (tap the right name of four) and "Name to
picture" (hear the name, tap the right flag or map of four).
"""

import csv
import html
import random
import sys
from pathlib import Path

import genanki

import word_decks

ROOT = Path(__file__).resolve().parent.parent
GEOGRAPHY = ROOT / "data" / "geography"

TOPICS = ("countries", "continents", "regions")

# Model and deck IDs are fixed forever; never change or reuse one.
MODEL_ID = 1987814188

# language -> (root deck, package, {picture kind: (subdeck name, deck ID)})
DECKS = {
    "sv": ("Geografi", "geography_sv.apkg",
           {"flag": ("Flaggor", 2016633135), "map": ("Kartor", 1195968314)}),
    "en": ("Geography", "geography_en.apkg",
           {"flag": ("Flags", 1679768671), "map": ("Maps", 2004765374)}),
    "de": ("Geografie", "geography_de.apkg",
           {"flag": ("Flaggen", 1577859751), "map": ("Karten", 1816058686)}),
    "sw": ("Jiografia", "geography_sw.apkg",
           {"flag": ("Bendera", 2056688592), "map": ("Ramani", 1882327794)}),
    "es": ("Geografía", "geography_es.apkg",
           {"flag": ("Banderas", 2083627779), "map": ("Mapas", 1642014553)}),
    "fr": ("Géographie", "geography_fr.apkg",
           {"flag": ("Drapeaux", 1869615827), "map": ("Cartes", 1522736478)}),
}

DESCRIPTION = {
    "sv": "Kids Flashcards, geografi: titta på flaggan eller kartan och tryck på rätt namn.",
    "en": "Kids Flashcards, geography: look at the flag or map and tap the right name.",
    "de": "Kids Flashcards, Geografie: schau die Flagge oder Karte an und tippe auf den "
          "richtigen Namen.",
    "sw": "Kids Flashcards, jiografia: tazama bendera au ramani na ubonyeze jina sahihi.",
    "es": "Kids Flashcards, geografía: mira la bandera o el mapa y toca el nombre correcto.",
    "fr": "Kids Flashcards, géographie : regarde le drapeau ou la carte et touche le bon nom.",
}


def read_places():
    """[(topic, row)] from data/geography/*.csv, checked like the concept tables."""
    places, seen = [], set()
    for path in sorted(GEOGRAPHY.glob("*.csv")):
        if path.stem not in TOPICS:
            sys.exit(f"{path.relative_to(ROOT)}: unknown geography topic (see geography_decks.TOPICS)")
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        for line, row in enumerate(rows, start=2):
            where = f"{path.relative_to(ROOT)}:{line}"
            if not row.get("id") or not row.get("level"):
                sys.exit(f"{where}: empty id or level")
            if row["id"] in seen:
                sys.exit(f"{where}: duplicate id {row['id']}")
            seen.add(row["id"])
            if not (row.get("flag") or row.get("map")):
                sys.exit(f"{where}: no flag or map picture")
            for lang in word_decks.LANGUAGES:
                if bool(row.get(lang)) != bool(row.get(f"audio_{lang}")):
                    sys.exit(f"{where}: {lang} needs both the name and audio_{lang}, or neither")
            if not any(row.get(lang) for lang in word_decks.LANGUAGES):
                sys.exit(f"{where}: no language has a recorded name")
            places.append((path.stem, row))
    return places


# Flags a child can't tell apart (Monaco and Indonesia are the same red over
# white): they are never offered as wrong choices for each other.
LOOKALIKES = [
    {"monaco", "indonesia"}, {"romania", "chad", "andorra", "moldova"},
    {"ireland", "ivory_coast", "italy"}, {"netherlands", "luxembourg", "paraguay"},
    {"australia", "new_zealand"}, {"senegal", "mali", "guinea"},
    {"colombia", "ecuador", "venezuela"}, {"slovakia", "slovenia", "russia", "serbia"},
    {"honduras", "nicaragua", "el_salvador"}, {"norway", "iceland"},
]


def lookalike(a, b):
    return any(a in group and b in group for group in LOOKALIKES)


def distractors(place, pool, lang, kind):
    """Three other names, picked stably per place, picture kind and language."""
    others = [p for p in pool if p["id"] != place["id"] and p[lang] != place[lang]
              and not (kind == "flag" and lookalike(p["id"], place["id"]))]
    return random.Random(f"geography:{place['id']}:{lang}").sample(others, 3)


def model(choices_js):
    tpl = ROOT / "templates" / "geography"
    label = (ROOT / "templates" / "picture_choice" / "language_label.html").read_text(encoding="utf-8")
    read = lambda name: ((tpl / name).read_text(encoding="utf-8")
                         .replace("{{CHOICES_JS}}", choices_js)
                         .replace("{{LANGUAGE_LABEL}}", label))
    return genanki.Model(
        MODEL_ID,
        "Kids Flashcards: Geography",
        fields=[{"name": "Name"}, {"name": "Picture"}, {"name": "Audio"},
                {"name": "NameChoices"}, {"name": "PictureChoices"}, {"name": "Credits"}],
        templates=[{
            "name": "Picture to name",
            "qfmt": read("picture_front.html"),
            "afmt": read("picture_back.html"),
        }, {
            "name": "Name to picture",
            "qfmt": read("name_front.html"),
            "afmt": read("name_back.html"),
        }],
        css=(tpl / "style.css").read_text(encoding="utf-8"),
    )


def build(langs=tuple(word_decks.LANGUAGES)):
    """Return {language: (decks, media files)} for the given languages."""
    if set(word_decks.LANGUAGES) - DECKS.keys():
        sys.exit(f"geography_decks.DECKS has no deck for "
                 f"{sorted(set(word_decks.LANGUAGES) - DECKS.keys())}")
    sources = word_decks.read_sources()
    places = read_places()
    choices_js = (ROOT / "templates" / "shapes" / "choices_script.html").read_text(encoding="utf-8")
    note_model = model(choices_js)
    button = '<button type="button" class="choice"{ok}>{content}</button>'
    labels = word_decks.LANGUAGES

    out = {}
    for lang in langs:
        root, _, subdecks = DECKS[lang]
        decks, files = [], set()
        for kind, (name, deck_id) in subdecks.items():
            rows = [(t, p) for t, p in places if p.get(lang) and p.get(kind)]
            if not rows:
                continue
            deck = genanki.Deck(deck_id, f"{root}::{name}",
                                description=f"{DESCRIPTION[lang]} {word_decks.LICENCE_NOTE}")
            for due, (topic, p) in enumerate(rows):
                # Wrong choices come from places of the same kind (countries
                # with countries), or from every place when that is too few.
                same = [q for t, q in rows if t == topic]
                pool = same if len(same) >= 4 else [q for _, q in rows]
                options = [p] + distractors(p, pool, lang, kind)
                images = [word_decks.media_file(sources, f"images/{o[kind]}") for o in options]
                audio = word_decks.media_file(sources, f"audio/{lang}/{p[f'audio_{lang}']}")
                files.update([*images, audio])
                ok = lambda o: ' data-ok="1"' if o is p else ""
                names = "".join(button.format(ok=ok(o), content=html.escape(o[lang]))
                                for o in options)
                pictures = "".join(button.format(ok=ok(o), content=f'<img src="{i.name}">')
                                   for o, i in zip(options, images))
                credits = (f"{labels[lang]['picture']}: "
                           f"{word_decks.credit(sources[f'images/{images[0].name}'])} · "
                           f"{labels[lang]['sound']}: "
                           f"{word_decks.credit(sources[f'audio/{lang}/{audio.name}'])}")
                deck.add_note(genanki.Note(
                    model=note_model,
                    fields=[html.escape(p[lang]), f'<img src="{images[0].name}">',
                            f"[sound:{audio.name}]", names, pictures, credits],
                    guid=genanki.guid_for("kids_flashcards", "geography", kind, p["id"], lang),
                    tags=[f"level{p['level']}", topic, kind, f"lang_{lang}"],
                    due=due,
                ))
            decks.append(deck)
        out[lang] = (decks, sorted(files))
        notes = sum(len(d.notes) for d in decks)
        print(f"{notes} {lang} places ({2 * notes} cards) in {len(decks)} geography subdecks")
    return out
