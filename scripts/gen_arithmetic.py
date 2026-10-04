#!/usr/bin/env python3
"""Generate the arithmetic tables in data/arithmetic/.

Each subdeck gets one CSV with the columns

    id, question, answer, distractors

`question` is ready to display (Unicode minus, times and division signs),
`answer` is a plain integer and `distractors` holds three wrong answers
separated by ';'. Rows are written easy-first, which is the order Anki shows
new cards in.

Everything is deterministic: rerunning the script produces identical files,
so the `id`s (and the Anki GUIDs derived from them) never change.

    python3 scripts/gen_arithmetic.py          # rewrite the CSVs
    python3 scripts/gen_arithmetic.py --check  # fail if the CSVs are stale
"""

import argparse
import csv
import io
import random
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "arithmetic"

MAX = 20            # largest term / factor used anywhere
THREE_TERM_COUNT = 220  # half of the 441 two-term addition cards
MINUS = "−"
TIMES = "×"
DIVIDE = "÷"


def num(n):
    """Display a number, wrapping negatives in brackets: 5 − (−3)."""
    return f"({MINUS}{-n})" if n < 0 else str(n)


# ---------------------------------------------------------------- distractors

def pick_distractors(card_id, answer, mistakes, allow_negative):
    """Pick three distinct wrong answers for a card.

    `mistakes` are errors a child plausibly makes for this kind of sum; up to
    two of them are used, the rest are near misses (answer ± 1..3). The pick
    is random but seeded by the card id, so it is stable between runs and the
    right answer is not always in the same place among the sorted choices.
    """
    rng = random.Random(f"distractors:{card_id}")
    ok = lambda n: n != answer and (allow_negative or n >= 0)

    picked = []
    mistakes = [m for m in dict.fromkeys(mistakes) if ok(m)]
    rng.shuffle(mistakes)
    picked.extend(mistakes[:2])

    near = [answer + d for d in (-3, -2, -1, 1, 2, 3)]
    near = [n for n in near if ok(n) and n not in picked]
    rng.shuffle(near)
    picked.extend(near[: 3 - len(picked)])

    step = 4
    while len(picked) < 3:  # only for answers near 0 with few candidates
        if ok(answer + step) and answer + step not in picked:
            picked.append(answer + step)
        step += 1
    return sorted(picked)


# ---------------------------------------------------------------------- cards

def add_card(*terms):
    answer = sum(terms)
    card_id = "add_" + "_".join(map(str, terms))
    question = " + ".join(map(str, terms))
    # Forgetting a term, or being off by ten when carrying.
    mistakes = [answer - t for t in terms if t]
    if answer >= 10:
        mistakes += [answer + 10, answer - 10]
    return card_id, question, answer, pick_distractors(card_id, answer, mistakes, False)


def sub_card(a, b):
    """a − b, where b may be negative (a double negation)."""
    answer = a - b
    card_id = f"sub_{a}_{b}".replace("-", "m")
    question = f"{num(a)} {MINUS} {num(b)}"
    allow_negative = answer < 0 or b < 0
    # Wrong sign, adding instead of subtracting, ignoring the double negative.
    mistakes = [-answer, a + b, b - a]
    return card_id, question, answer, pick_distractors(card_id, answer, mistakes, allow_negative)


def mul_card(a, b):
    answer = a * b
    card_id = f"mul_{a}_{b}"
    question = f"{a} {TIMES} {b}"
    # Neighbouring table entries, and adding instead of multiplying.
    mistakes = [(a + 1) * b, (a - 1) * b, a * (b + 1), a * (b - 1), a + b]
    return card_id, question, answer, pick_distractors(card_id, answer, mistakes, False)


def div_card(a, b):
    answer = a // b
    card_id = f"div_{a}_{b}"
    question = f"{a} {DIVIDE} {b}"
    # Answering with the divisor, or subtracting instead of dividing.
    mistakes = [b, a - b]
    return card_id, question, answer, pick_distractors(card_id, answer, mistakes, False)


def easy_first(pairs):
    """Order operand tuples so small numbers come first."""
    return sorted(pairs, key=lambda t: (max(map(abs, t)), sum(map(abs, t)), t))


R = range(MAX + 1)


def two_term_addition():
    pairs = [(a, b) for a in R for b in R]
    return {
        "addition_1_sums_to_10": [add_card(*p) for p in easy_first(p for p in pairs if sum(p) <= 10)],
        "addition_2_sums_to_20": [add_card(*p) for p in easy_first(p for p in pairs if 10 < sum(p) <= 20)],
        "addition_3_terms_to_20": [add_card(*p) for p in easy_first(p for p in pairs if sum(p) > 20)],
    }


def three_term_addition():
    triples = [(a, b, c) for a in range(1, MAX + 1) for b in range(1, MAX + 1)
               for c in range(1, MAX + 1) if a + b + c <= MAX]
    sample = random.Random("addition_three_terms").sample(triples, THREE_TERM_COUNT)
    return {"addition_4_three_terms": [add_card(*t) for t in easy_first(sample)]}


def subtraction():
    pairs = [(a, b) for a in R for b in R]
    nonneg = [p for p in pairs if p[0] >= p[1]]
    neg = [p for p in pairs if p[0] < p[1]]
    double = [(a, -b) for a in R for b in range(1, MAX + 1)]
    return {
        "subtraction_1_within_10": [sub_card(*p) for p in easy_first(p for p in nonneg if p[0] <= 10)],
        "subtraction_2_within_20": [sub_card(*p) for p in easy_first(p for p in nonneg if p[0] > 10)],
        "subtraction_3_negative_within_10": [sub_card(*p) for p in easy_first(p for p in neg if p[1] <= 10)],
        "subtraction_4_negative_within_20": [sub_card(*p) for p in easy_first(p for p in neg if p[1] > 10)],
        "subtraction_5_double_negative_to_10": [sub_card(*p) for p in easy_first(p for p in double if p[0] - p[1] <= 10)],
        "subtraction_6_double_negative_to_20": [sub_card(*p) for p in easy_first(p for p in double if 10 < p[0] - p[1] <= 20)],
        "subtraction_7_double_negative_terms_to_20": [sub_card(*p) for p in easy_first(p for p in double if p[0] - p[1] > 20)],
    }


def multiplication():
    pairs = [(a, b) for a in R for b in R]
    return {
        "multiplication_1_tables_to_10": [mul_card(*p) for p in easy_first(p for p in pairs if max(p) <= 10)],
        "multiplication_2_tables_to_20": [mul_card(*p) for p in easy_first(p for p in pairs if max(p) > 10)],
    }


def division():
    # Dividend and divisor both 0-20, whole-number answers, never ÷ 0.
    pairs = [(a, b) for a in R for b in range(1, MAX + 1) if a % b == 0]
    return {"division_1_within_20": [div_card(*p) for p in easy_first(pairs)]}


def all_tables():
    tables = {}
    for part in (two_term_addition, three_term_addition, subtraction, multiplication, division):
        tables.update(part())
    ids = [row[0] for rows in tables.values() for row in rows]
    assert len(ids) == len(set(ids)), "duplicate card id"
    return tables


def render(rows):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["id", "question", "answer", "distractors"])
    for card_id, question, answer, distractors in rows:
        writer.writerow([card_id, question, answer, ";".join(map(str, distractors))])
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if data/arithmetic/ differs from what would be generated")
    args = parser.parse_args()

    tables = {name: render(rows) for name, rows in all_tables().items()}
    expected = {OUT_DIR / f"{name}.csv": text for name, text in tables.items()}
    existing = set(OUT_DIR.glob("*.csv")) if OUT_DIR.exists() else set()

    if args.check:
        stale = [p for p, text in expected.items()
                 if not p.exists() or p.read_text(encoding="utf-8") != text]
        stale += sorted(existing - expected.keys())
        for p in stale:
            print(f"stale: {p.relative_to(OUT_DIR.parent.parent)}", file=sys.stderr)
        sys.exit(1 if stale else 0)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p in existing - expected.keys():
        p.unlink()
    total = 0
    for p, text in expected.items():
        p.write_text(text, encoding="utf-8")
        n = text.count("\n") - 1
        total += n
        print(f"{n:4d}  {p.name}")
    print(f"{total:4d}  total")


if __name__ == "__main__":
    main()
