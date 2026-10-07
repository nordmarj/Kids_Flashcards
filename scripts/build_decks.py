#!/usr/bin/env python3
"""Build Anki decks from data/ into build/*.apkg.

So far this builds the arithmetic deck: one .apkg whose subdecks are the
CSV files in data/arithmetic/ (written by gen_arithmetic.py). Every sum
gets two cards: "Choose the answer" (multiple choice) and "Type the
answer". To use only one style, suspend the other in Anki's browser,
e.g. search `card:Type*`.

    python3 scripts/build_decks.py
"""

import csv
import sys
from pathlib import Path

import genanki

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build"
MINUS = "−"

# Model and deck IDs are fixed forever: changing one makes Anki treat the
# note type or deck as new. Add new subdecks with fresh IDs; never reuse one.
ARITHMETIC_MODEL_ID = 1904249263

# CSV name in data/arithmetic/ -> (Anki deck name, deck ID)
ARITHMETIC_DECKS = {
    "addition_1_sums_to_10": ("Arithmetic::1 Addition::1 Sums to 10", 1868921369),
    "addition_2_sums_to_20": ("Arithmetic::1 Addition::2 Sums to 20", 1077415841),
    "addition_3_terms_to_20": ("Arithmetic::1 Addition::3 Numbers to 20", 1654720591),
    "addition_4_three_terms": ("Arithmetic::1 Addition::4 Three numbers", 1566316843),
    "subtraction_1_within_10": ("Arithmetic::2 Subtraction::1 Within 10", 1684420497),
    "subtraction_2_within_20": ("Arithmetic::2 Subtraction::2 Within 20", 1476934939),
    "subtraction_3_negative_within_10": ("Arithmetic::2 Subtraction::3 Below zero, to 10", 1245795202),
    "subtraction_4_negative_within_20": ("Arithmetic::2 Subtraction::4 Below zero, to 20", 1574362976),
    "subtraction_5_double_negative_to_10": ("Arithmetic::2 Subtraction::5 Minus a negative, to 10", 1116905626),
    "subtraction_6_double_negative_to_20": ("Arithmetic::2 Subtraction::6 Minus a negative, to 20", 1110041737),
    "subtraction_7_double_negative_terms_to_20": ("Arithmetic::2 Subtraction::7 Minus a negative, numbers to 20", 1771736042),
    "multiplication_1_tables_to_10": ("Arithmetic::3 Multiplication::1 Tables 0-10", 1367887976),
    "multiplication_2_tables_to_20": ("Arithmetic::3 Multiplication::2 Tables to 20", 1238147049),
    "division_1_within_20": ("Arithmetic::4 Division::1 Within 20", 1581320197),
    "division_2_tables_backwards": ("Arithmetic::4 Division::2 Tables backwards", 1224304286),
}

DECK_DESCRIPTION = (
    "Kids Flashcards, arithmetic. Each sum has two cards: tap the right answer, "
    "and type the answer. "
    "Released under CC BY-NC-SA 4.0: https://github.com/nordmarj/Kids_Flashcards"
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
                {"name": "TypeAnswer"}],
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
                fields=[question, fmt(answer), choices, str(answer)],
                guid=genanki.guid_for("kids_flashcards", "arithmetic", card_id),
                due=due,  # new cards are shown easy-first, in CSV order
            ))
        decks.append(deck)

    BUILD_DIR.mkdir(exist_ok=True)
    out = BUILD_DIR / "arithmetic.apkg"
    genanki.Package(decks).write_to_file(out)
    print(f"{len(seen)} sums ({2 * len(seen)} cards) in {len(decks)} subdecks -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    build_arithmetic()
