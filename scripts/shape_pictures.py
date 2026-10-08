"""Pictures of geometric shapes, drawn as inline SVG.

`picture(shape_id)` returns an <svg> string for an id in data/shapes/shapes.csv.
Every shape uses the same colour, so a child has to tell them apart by form.
"""

import math

FILL = "#2f6fdd"
LIGHT = "#7aa6f2"
DARK = "#1f4fa8"
STROKE = "#173a7a"
SW = 2.5  # stroke width


def _svg(body, size=96):
    return (f'<svg class="shape" viewBox="0 0 100 100" width="{size}" height="{size}" '
            f'xmlns="http://www.w3.org/2000/svg" stroke="{STROKE}" stroke-width="{SW}" '
            f'stroke-linejoin="round">{body}</svg>')


def _points(pts):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def _polygon(pts, fill=FILL):
    return f'<polygon points="{_points(pts)}" fill="{fill}"/>'


def _regular(n, r=42, cx=50, cy=52):
    # Rotated so the bottom edge is flat.
    start = math.pi / 2 + math.pi / n
    return [(cx + r * math.cos(start + 2 * math.pi * k / n),
             cy + r * math.sin(start + 2 * math.pi * k / n)) for k in range(n)]


def _star(cx=50, cy=54, outer=44, inner=18):
    pts = []
    for k in range(10):
        r = outer if k % 2 == 0 else inner
        a = -math.pi / 2 + math.pi * k / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


SHAPES = {
    "circle": f'<circle cx="50" cy="50" r="40" fill="{FILL}"/>',
    "square": f'<rect x="14" y="14" width="72" height="72" fill="{FILL}"/>',
    "triangle": _polygon([(50, 12), (92, 84), (8, 84)]),
    "rectangle": f'<rect x="6" y="28" width="88" height="44" fill="{FILL}"/>',
    "oval": f'<ellipse cx="50" cy="50" rx="44" ry="27" fill="{FILL}"/>',
    "star": _polygon(_star()),
    "heart": (f'<path d="M50 88C22 68 6 50 12 31C18 13 42 11 50 29C58 11 82 13 88 31'
              f'C94 50 78 68 50 88Z" fill="{FILL}"/>'),
    "diamond": _polygon([(50, 6), (82, 50), (50, 94), (18, 50)]),
    "pentagon": _polygon(_regular(5)),
    "hexagon": _polygon(_regular(6, cy=50)),
    "octagon": _polygon(_regular(8, cy=50)),
    "semicircle": f'<path d="M8 70A42 42 0 0 1 92 70Z" fill="{FILL}"/>',
    "trapezoid": _polygon([(30, 24), (70, 24), (94, 76), (6, 76)]),
    "parallelogram": _polygon([(30, 26), (96, 26), (70, 74), (4, 74)]),
    # Solid shapes: lighter top faces and darker sides suggest depth.
    "cube": (_polygon([(12, 36), (64, 36), (64, 88), (12, 88)]) +
             _polygon([(12, 36), (36, 14), (88, 14), (64, 36)], LIGHT) +
             _polygon([(64, 36), (88, 14), (88, 66), (64, 88)], DARK)),
    "sphere": ('<defs><radialGradient id="kf-sphere" cx="0.35" cy="0.32" r="0.75">'
               f'<stop offset="0" stop-color="#d6e4fb"/><stop offset="0.45" stop-color="{FILL}"/>'
               f'<stop offset="1" stop-color="{DARK}"/></radialGradient></defs>'
               '<circle cx="50" cy="50" r="40" fill="url(#kf-sphere)"/>'),
    "cylinder": (f'<path d="M20 24V78A30 10 0 0 0 80 78V24Z" fill="{FILL}"/>'
                 f'<ellipse cx="50" cy="24" rx="30" ry="10" fill="{LIGHT}"/>'),
    "cone": (f'<path d="M50 8L82 80A32 11 0 0 1 18 80Z" fill="{FILL}"/>'
             f'<path d="M18 80A32 11 0 0 0 82 80" fill="none"/>'),
    "pyramid": (_polygon([(50, 10), (14, 80), (60, 92)]) +
                _polygon([(50, 10), (60, 92), (88, 74)], DARK)),
}


def picture(shape_id, size=96):
    return _svg(SHAPES[shape_id], size)
