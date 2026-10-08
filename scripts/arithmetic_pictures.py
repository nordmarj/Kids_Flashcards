"""Counting pictures for arithmetic cards, drawn as inline SVG.

`picture(card_id)` returns an <svg> string, or "" when no picture helps
(zero products, tables beyond 10). The card id says what to draw:

    add_3_4 / add_2_5_1   dots in ten-frames, one colour per number
    sub_7_3               7 dots in ten-frames, the last 3 crossed out
    sub_3_7, sub_5_m3     a number line with a jump (negatives involved)
    mul_3_4               3 rows of 4 dots
    div_12_3              12 dots shared into 3 rows

Pictures are pure SVG with fixed colours, so they need no media files and
look the same on Anki desktop, AnkiDroid and AnkiMobile.
"""

COLOURS = ["#2f6fdd", "#f08c00", "#2b9a3e"]  # one per term
CROSSED = "#9e9e9e"
LINE = "#888"
TEXT = "#888"

CELL = 26     # ten-frame cell size
DOT_R = 9
FRAME_GAP = 12
MAX_ARRAY = 10  # largest side of a multiplication/division array


def _svg(width, height, body):
    return (f'<svg class="picture" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
            f'{body}</svg>')


def _dot(cx, cy, fill):
    return f'<circle cx="{cx}" cy="{cy}" r="{DOT_R}" fill="{fill}"/>'


def _crossed(cx, cy):
    d = DOT_R - 2
    return (f'<circle cx="{cx}" cy="{cy}" r="{DOT_R}" fill="none" stroke="{CROSSED}" stroke-width="2"/>'
            f'<path d="M{cx - d} {cy - d}L{cx + d} {cy + d}M{cx + d} {cy - d}L{cx - d} {cy + d}" '
            f'stroke="{CROSSED}" stroke-width="2.5" stroke-linecap="round"/>')


def ten_frames(dots):
    """Draw dots into ten-frames (2 rows of 5), two frames side by side.

    `dots` is a list of colours, or None for a crossed-out dot.
    """
    frames = max(1, -(-len(dots) // 10))
    per_row = min(frames, 2)
    rows = -(-frames // 2)
    fw, fh = 5 * CELL, 2 * CELL
    width = per_row * fw + (per_row - 1) * FRAME_GAP + 4
    height = rows * fh + (rows - 1) * FRAME_GAP + 4
    body = []
    for f in range(frames):
        x0 = 2 + (f % 2) * (fw + FRAME_GAP)
        y0 = 2 + (f // 2) * (fh + FRAME_GAP)
        body.append(f'<rect x="{x0}" y="{y0}" width="{fw}" height="{fh}" rx="4" '
                    f'fill="none" stroke="{LINE}" stroke-width="1.5"/>')
        body.append(f'<path d="M{x0} {y0 + CELL}h{fw}' +
                    "".join(f"M{x0 + i * CELL} {y0}v{fh}" for i in range(1, 5)) +
                    f'" stroke="{LINE}" stroke-width="1" opacity="0.6"/>')
    for i, colour in enumerate(dots):
        f, k = divmod(i, 10)
        cx = 2 + (f % 2) * (fw + FRAME_GAP) + (k % 5) * CELL + CELL // 2
        cy = 2 + (f // 2) * (fh + FRAME_GAP) + (k // 5) * CELL + CELL // 2
        body.append(_crossed(cx, cy) if colour is None else _dot(cx, cy, colour))
    return _svg(width, height, "".join(body))


def dot_array(rows, cols, colours=None):
    """`rows` rows of `cols` dots, with a small gap after every fifth row
    and column so bigger arrays are easy to count. Each row may get its
    own colour."""
    gap = 6
    pos = lambda i: 2 + i * CELL + (i // 5) * gap + CELL // 2
    width = pos(cols - 1) + CELL // 2 + 2
    height = pos(rows - 1) + CELL // 2 + 2
    body = []
    for r in range(rows):
        colour = colours[r % len(colours)] if colours else COLOURS[0]
        for c in range(cols):
            body.append(_dot(pos(c), pos(r), colour))
    return _svg(width, height, "".join(body))


def number_line(start, jump):
    """A number line with an arrow from `start` jumping by `jump`."""
    end = start + jump
    lo, hi = min(0, start, end), max(0, start, end)
    step = 18 if hi - lo <= 20 else 9
    pad = 16
    width = (hi - lo) * step + 2 * pad
    height = 74
    axis_y = 46
    x = lambda n: pad + (n - lo) * step
    body = [f'<path d="M{x(lo) - 8} {axis_y}H{x(hi) + 8}" stroke="{LINE}" stroke-width="2"/>']
    for n in range(lo, hi + 1):
        tall = n == 0 or n % 5 == 0
        body.append(f'<path d="M{x(n)} {axis_y - (6 if tall else 3)}v{12 if tall else 6}" '
                    f'stroke="{LINE}" stroke-width="{2 if n == 0 else 1}"/>')
    labels = sorted({0, start, end} | ({lo, hi} if hi - lo > 5 else set()))
    for n in labels:
        label = f"−{-n}" if n < 0 else str(n)
        weight = ' font-weight="bold"' if n in (start, end) else ""
        body.append(f'<text x="{x(n)}" y="{axis_y + 24}" font-size="13" text-anchor="middle" '
                    f'fill="{TEXT}" font-family="sans-serif"{weight}>{label}</text>')
    # The jump: an arc from start to end with an arrow head at the end.
    x1, x2 = x(start), x(end)
    mid, top = (x1 + x2) / 2, 6
    colour = COLOURS[1]
    body.append(f'<path d="M{x1} {axis_y - 4}Q{mid} {top} {x2} {axis_y - 4}" fill="none" '
                f'stroke="{colour}" stroke-width="3"/>')
    head = 7 if x2 > x1 else -7
    body.append(f'<path d="M{x2} {axis_y - 3}l{-head} -9M{x2} {axis_y - 3}l{-head * 0.2:.1f} -11" '
                f'stroke="{colour}" stroke-width="3" stroke-linecap="round"/>')
    body.append(_dot(x1, axis_y, COLOURS[0]))
    return _svg(width, height, "".join(body))


def picture(card_id):
    op, *nums = card_id.split("_")
    nums = [-int(n[1:]) if n.startswith("m") else int(n) for n in nums]
    if op == "add":
        dots = [COLOURS[i] for i, n in enumerate(nums) for _ in range(n)]
        return ten_frames(dots) if dots else ""
    if op == "sub":
        a, b = nums
        if 0 <= b <= a:
            return ten_frames([COLOURS[0]] * (a - b) + [None] * b) if a else ""
        return number_line(a, -b)
    if op == "mul":
        a, b = nums
        if a and b and max(a, b) <= MAX_ARRAY:
            return dot_array(a, b)
        return ""
    if op == "div":
        a, b = nums
        q = a // b
        if a and max(b, q) <= MAX_ARRAY:
            return dot_array(b, q, COLOURS)
        return ""
    raise ValueError(f"no picture rule for {card_id}")
