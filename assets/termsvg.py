"""Draws a terminal window as an SVG, on a fixed character grid.

GitHub renders README code blocks in the *viewer's* theme and strips colour, so
the cards on the profile README are SVGs instead: they carry their own black
background and look the same in light mode, dark mode and dimmed.

A row is a list of (column, text, colour) runs. Every run is pinned to the grid
with textLength, so columns stay aligned even where the viewer resolves a
different monospace face.
"""

CHAR_W, LINE_H, FONT_SIZE = 8.4, 20.0, 14
PAD_X, PAD_TOP, TITLEBAR = 22.0, 16.0, 34.0

BG     = "#0d0f10"          # window body — black, on purpose
CHROME = "#1b1d1e"          # title bar
BORDER = "#2b2e30"
TRACK  = "#24282a"          # unfilled part of a meter
GREEN  = "#23e298"          # matches provadigital.com.br's prompt
ORANGE = "#d08010"
GREY   = "#bbbbbb"
DIM    = "#6f7275"
CYAN   = "#66d9ef"
PINK   = "#f92672"
PURPLE = "#ae81ff"

FONT = ('ui-monospace, SFMono-Regular, &quot;SF Mono&quot;, Menlo, Consolas, '
        '&quot;DejaVu Sans Mono&quot;, monospace')

USER = "charles.santos@t7"


def prompt(command=None, col=0):
    """The PS1, optionally followed by a command, as positioned runs."""
    runs = [(col, USER, GREEN), (col + len(USER), ":", GREY),
            (col + len(USER) + 1, "~", ORANGE), (col + len(USER) + 2, "$", GREY)]
    if command:
        runs.append((col + len(USER) + 4, command, GREY))
    return runs


class Bar:
    """A meter drawn as real rectangles. Block characters (\u2588 \u2591) were tried
    first, but the light-shade glyph renders as a noisy dither in most faces."""

    def __init__(self, col, width, fraction, colour, track=TRACK):
        self.col, self.width = col, width
        self.fraction = max(0.0, min(1.0, fraction))
        self.colour, self.track = colour, track


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(rows, path, title, cursor=None, min_cols=0):
    """rows: list of rows, each a list of (col, text, colour).
       cursor: (row_index, col) to park a blinking block, or None.
       min_cols: pad the window out to at least this many columns, so cards
                 stacked in the same README share one width."""
    def extent(item):
        return item.col + item.width if isinstance(item, Bar) else item[0] + len(item[1])

    cols = max([extent(i) for row in rows for i in row] + [min_cols], default=0)
    width = PAD_X * 2 + cols * CHAR_W
    height = TITLEBAR + PAD_TOP + len(rows) * LINE_H + 10

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="{FONT}" font-size="{FONT_SIZE}" '
        f'role="img" aria-label="{esc(title)}">',
        f'<rect width="{width:.0f}" height="{height:.0f}" rx="8" fill="{BG}" stroke="{BORDER}"/>',
        f'<path d="M0 8a8 8 0 0 1 8-8h{width - 16:.0f}a8 8 0 0 1 8 8v{TITLEBAR - 8:.0f}H0z" fill="{CHROME}"/>',
        f'<line x1="0" y1="{TITLEBAR}" x2="{width:.0f}" y2="{TITLEBAR}" stroke="{BORDER}"/>',
    ]
    for i, colour in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        out.append(f'<circle cx="{22 + i * 18}" cy="{TITLEBAR / 2:.0f}" r="6" fill="{colour}"/>')
    out.append(
        f'<text x="{width / 2:.0f}" y="{TITLEBAR / 2 + 4:.0f}" fill="{DIM}" font-size="12" '
        f'text-anchor="middle">{esc(title)}</text>'
    )

    for i, row in enumerate(rows):
        y = TITLEBAR + PAD_TOP + i * LINE_H + FONT_SIZE
        for item in row:
            if isinstance(item, Bar):
                x, w = PAD_X + item.col * CHAR_W, item.width * CHAR_W
                out.append(f'<rect x="{x:.1f}" y="{y - 10:.1f}" width="{w:.1f}" height="10" '
                           f'rx="2" fill="{item.track}"/>')
                if item.fraction > 0:
                    out.append(f'<rect x="{x:.1f}" y="{y - 10:.1f}" width="{w * item.fraction:.1f}" '
                               f'height="10" rx="2" fill="{item.colour}"/>')
                continue
            col, text, colour = item
            out.append(
                f'<text xml:space="preserve" x="{PAD_X + col * CHAR_W:.1f}" y="{y:.1f}" '
                f'fill="{colour}" textLength="{len(text) * CHAR_W:.1f}" '
                f'lengthAdjust="spacingAndGlyphs">{esc(text)}</text>'
            )

    if cursor:
        row_i, col = cursor
        out.append(
            f'<rect x="{PAD_X + col * CHAR_W:.1f}" y="{TITLEBAR + PAD_TOP + row_i * LINE_H + 3:.1f}" '
            f'width="{CHAR_W:.1f}" height="{FONT_SIZE + 2}" fill="{GREEN}">'
            f'<animate attributeName="opacity" values="1;1;0;0" dur="1.06s" repeatCount="indefinite"/></rect>'
        )

    out.append("</svg>")
    svg = "\n".join(out) + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"{path}  {width:.0f}x{height:.0f}  {len(rows)} rows, {cols} cols, {len(svg)} bytes")
