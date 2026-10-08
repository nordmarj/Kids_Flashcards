#!/usr/bin/env python3
"""Build Anki decks from data/ into build/*.apkg.

Builds build/svenska.apkg and build/english.apkg (picture → word cards, see
word_decks.py) and build/maths.apkg, one "Maths" deck with these subdecks:

- Arithmetic: one subdeck per CSV file in data/arithmetic/ (written by
  gen_arithmetic.py). Every sum gets two cards: "Choose the answer"
  (multiple choice) and "Type the answer". To use only one style, suspend
  the other in Anki's browser, e.g. search `card:Type*`.
- Shapes: data/shapes/shapes.csv, one subdeck per language. Every shape
  gets two multiple-choice cards: "Name to picture" and "Picture to name".

    python3 scripts/build_decks.py
"""

import csv
import html
import random
import sys
from pathlib import Path

import genanki

import shape_pictures
import word_decks
from arithmetic_pictures import picture

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build"
MINUS = "−"

# Model and deck IDs are fixed forever: changing one makes Anki treat the
# note type or deck as new. Add new subdecks with fresh IDs; never reuse one.
ARITHMETIC_MODEL_ID = 1904249263

# CSV name in data/arithmetic/ -> (Anki deck name, deck ID)
ARITHMETIC_DECKS = {
    "addition_1_sums_to_10": ("Maths::1 Addition::1 Sums to 10", 1868921369),
    "addition_2_sums_to_20": ("Maths::1 Addition::2 Sums to 20", 1077415841),
    "addition_3_terms_to_20": ("Maths::1 Addition::3 Numbers to 20", 1654720591),
    "addition_4_three_terms": ("Maths::1 Addition::4 Three numbers", 1566316843),
    "subtraction_1_within_10": ("Maths::2 Subtraction::1 Within 10", 1684420497),
    "subtraction_2_within_20": ("Maths::2 Subtraction::2 Within 20", 1476934939),
    "subtraction_3_negative_within_10": ("Maths::2 Subtraction::3 Below zero, to 10", 1245795202),
    "subtraction_4_negative_within_20": ("Maths::2 Subtraction::4 Below zero, to 20", 1574362976),
    "subtraction_5_double_negative_to_10": ("Maths::2 Subtraction::5 Minus a negative, to 10", 1116905626),
    "subtraction_6_double_negative_to_20": ("Maths::2 Subtraction::6 Minus a negative, to 20", 1110041737),
    "subtraction_7_double_negative_terms_to_20": ("Maths::2 Subtraction::7 Minus a negative, numbers to 20", 1771736042),
    "multiplication_1_tables_to_10": ("Maths::3 Multiplication::1 Tables 0-10", 1367887976),
    "multiplication_2_tables_to_20": ("Maths::3 Multiplication::2 Tables to 20", 1238147049),
    "division_1_within_20": ("Maths::4 Division::1 Within 20", 1581320197),
    "division_2_tables_backwards": ("Maths::4 Division::2 Tables backwards", 1224304286),
}

SHAPES_MODEL_ID = 1988648040
# language -> (Anki deck name, deck ID)
SHAPES_DECKS = {
    "en": ("Maths::5 Shapes", 1748236718),
    "sv": ("Maths::6 Former (svenska)", 1330122437),
}

LICENCE_NOTE = "Released under CC BY-NC-SA 4.0: https://github.com/nordmarj/Kids_Flashcards"
DECK_DESCRIPTION = (
    "Kids Flashcards, arithmetic. Each sum has two cards: tap the right answer, "
    "and type the answer. " + LICENCE_NOTE
)
SHAPES_DESCRIPTION = (
    "Kids Flashcards, shapes. Tap the picture that matches the name, and the "
    "name that matches the picture. " + LICENCE_NOTE
)


def fmt(n):
    """Display an integer with a real minus sign."""
    return f"{MINUS}{-n}" if n < 0 else str(n)


def arithmetic_model():
    tpl = ROOT / "templates" / "arithmetic"
    return genanki.Model(
        ARITHMETIC_MODEL_ID,
        "Kids Flashcards: Arithmetic",
        fields=[{"name": "Question"}, {"name": "Answer"}, {"name": "Choices"},
                {"name": "TypeAnswer"}, {"name": "Picture"}],
        templates=[{
            "name": "Choose the answer",
            "qfmt": (tpl / "front.html").read_text(encoding="utf-8"),
            "afmt": (tpl / "back.html").read_text(encoding="utf-8"),
        }, {
            "name": "Type the answer",
            "qfmt": (tpl / "type_front.html").read_text(encoding="utf-8"),
            "afmt": (tpl / "type_back.html").read_text(encoding="utf-8"),
        }],
        css=(tpl / "style.css").read_text(encoding="utf-8"),
    )


def read_arithmetic(path):
    """Read one arithmetic CSV, failing loudly on malformed rows."""
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for line, row in enumerate(csv.DictReader(f), start=2):
            where = f"{path.relative_to(ROOT)}:{line}"
            answer = int(row["answer"])
            distractors = [int(d) for d in row["distractors"].split(";")]
            if len(set(distractors)) != 3 or answer in distractors:
                sys.exit(f"{where}: need 3 distinct distractors different from the answer")
            rows.append((row["id"], row["question"], answer, distractors))
    return rows


def build_arithmetic():
    data_dir = ROOT / "data" / "arithmetic"
    found = {p.stem for p in data_dir.glob("*.csv")}
    if found != ARITHMETIC_DECKS.keys():
        sys.exit(f"data/arithmetic/ and ARITHMETIC_DECKS disagree: "
                 f"unconfigured {sorted(found - ARITHMETIC_DECKS.keys())}, "
                 f"missing {sorted(ARITHMETIC_DECKS.keys() - found)}")

    model = arithmetic_model()
    decks, seen = [], set()
    for stem, (name, deck_id) in ARITHMETIC_DECKS.items():
        deck = genanki.Deck(deck_id, name, description=DECK_DESCRIPTION)
        for due, (card_id, question, answer, distractors) in enumerate(
                read_arithmetic(data_dir / f"{stem}.csv")):
            if card_id in seen:
                sys.exit(f"duplicate id {card_id}")
            seen.add(card_id)
            choices = ";".join(fmt(n) for n in sorted([answer] + distractors))
            deck.add_note(genanki.Note(
                model=model,
                # TypeAnswer uses a plain "-" so it matches what a keyboard types.
                fields=[question, fmt(answer), choices, str(answer), picture(card_id)],
                guid=genanki.guid_for("kids_flashcards", "arithmetic", card_id),
                due=due,  # new cards are shown easy-first, in CSV order
            ))
        decks.append(deck)

    print(f"{len(seen)} sums ({2 * len(seen)} cards) in {len(decks)} arithmetic subdecks")
    return decks


def shapes_model():
    tpl = ROOT / "templates" / "shapes"
    script = (tpl / "choices_script.html").read_text(encoding="utf-8")
    read = lambda name: (tpl / name).read_text(encoding="utf-8").replace("{{CHOICES_JS}}", script)
    return genanki.Model(
        SHAPES_MODEL_ID,
        "Kids Flashcards: Shapes",
        fields=[{"name": "Name"}, {"name": "Picture"}, {"name": "Audio"},
                {"name": "NameChoices"}, {"name": "PictureChoices"}, {"name": "Credits"}],
        templates=[{
            "name": "Name to picture",
            "qfmt": read("name_front.html"),
            "afmt": read("name_back.html"),
        }, {
            "name": "Picture to name",
            "qfmt": read("picture_front.html"),
            "afmt": read("picture_back.html"),
        }],
        css=(tpl / "style.css").read_text(encoding="utf-8"),
    )


def shape_distractors(shape, shapes):
    """Three other shapes of the same level, picked stably per shape."""
    pool = [s for s in shapes if s["level"] == shape["level"] and s["id"] != shape["id"]]
    return random.Random(f"shapes:{shape['id']}").sample(pool, 3)


def build_shapes():
    """Shape decks and the audio files they use."""
    with (ROOT / "data" / "shapes" / "shapes.csv").open(encoding="utf-8", newline="") as f:
        shapes = list(csv.DictReader(f))
    for s in shapes:
        if not (s["id"] and s["sv"] and s["en"]) or s["id"] not in shape_pictures.SHAPES:
            sys.exit(f"shapes.csv: incomplete row or no picture for {s}")

    # Audio is optional here: not every shape name has a recording yet.
    sources = word_decks.read_sources()
    model = shapes_model()
    button = '<button type="button" class="choice"{ok}>{content}</button>'
    decks, media = [], set()
    for lang, (name, deck_id) in SHAPES_DECKS.items():
        deck = genanki.Deck(deck_id, name, description=SHAPES_DESCRIPTION)
        for due, shape in enumerate(shapes):
            options = [shape] + shape_distractors(shape, shapes)
            ok = lambda o: ' data-ok="1"' if o is shape else ""
            names = "".join(button.format(ok=ok(o), content=html.escape(o[lang])) for o in options)
            pictures = "".join(button.format(ok=ok(o), content=shape_pictures.picture(o["id"]))
                               for o in options)
            sound = credits = ""
            if shape.get(f"audio_{lang}"):
                rel = f"audio/{lang}/{shape[f'audio_{lang}']}"
                media.add(word_decks.media_file(sources, rel))
                sound = f"[sound:{shape[f'audio_{lang}']}]"
                label = "Ljud" if lang == "sv" else "Sound"
                credits = f"{label}: {word_decks.credit(sources[rel])}"
            deck.add_note(genanki.Note(
                model=model,
                fields=[html.escape(shape[lang]), shape_pictures.picture(shape["id"]), sound,
                        names, pictures, credits],
                guid=genanki.guid_for("kids_flashcards", "shapes", shape["id"], lang),
                due=due,
            ))
        decks.append(deck)
    print(f"{len(shapes)} shapes ({4 * len(shapes)} cards) in {len(decks)} language subdecks, "
          f"{len(media)} recordings")
    return decks, media


def main():
    BUILD_DIR.mkdir(exist_ok=True)
    for lang, (decks, media) in word_decks.build().items():
        out = BUILD_DIR / word_decks.PACKAGES[lang]
        genanki.Package(decks, media_files=[str(m) for m in media]).write_to_file(out)
        print(f"-> {out.relative_to(ROOT)}")

    shape_decks, shape_media = build_shapes()
    out = BUILD_DIR / "maths.apkg"
    genanki.Package(build_arithmetic() + shape_decks,
                    media_files=[str(m) for m in sorted(shape_media)]).write_to_file(out)
    print(f"-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
