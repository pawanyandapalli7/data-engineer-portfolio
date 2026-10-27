"""
Builds assets/banner-light.svg and assets/banner-dark.svg.

Text is converted to outlines (Manrope + JetBrains Mono, both OFL) so the banner
looks the same on every machine; GitHub can't load web fonts inside an SVG.

    pip install fonttools
    curl -LO "https://raw.githubusercontent.com/google/fonts/main/ofl/manrope/Manrope%5Bwght%5D.ttf"
    curl -LO "https://raw.githubusercontent.com/google/fonts/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf"
    python assets/build_banner.py --manrope "Manrope[wght].ttf" --mono "JetBrainsMono[wght].ttf"
"""

import argparse
from functools import cache
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

OUT = Path(__file__).resolve().parent
W, H = 1280, 400
TRACK_Y = 300
X0, X1 = 64, 1216
STATIONS = [  # (x, name, what happens there, colour token)
    (140, "landing", "files as delivered", "muted"),
    (420, "bronze", "as landed + lineage", "bronze"),
    (700, "silver", "typed, deduped, checked", "silver"),
    (980, "gold", "SCD2 dims + facts", "gold"),
]
Q_X, Q_Y = 860, 368  # quarantine station
Q_NOTE = "kept, with the checks it failed"
TAGLINE = "Data and ML platforms on Azure Databricks, Snowflake and AWS"

THEMES = {
    "light": dict(
        bg="#F4EFE2",
        ink="#17332A",
        muted="#5E7268",
        track="#17332A",
        bronze="#A0612F",
        silver="#7F8C88",
        gold="#B0851C",
        reject="#B4472F",
        packet="#17332A",
    ),
    "dark": dict(
        bg="#0E1F18",
        ink="#EFE8D6",
        muted="#9DB0A5",
        track="#EFE8D6",
        bronze="#D08F58",
        silver="#C3CCC8",
        gold="#E3B94B",
        reject="#E2765B",
        packet="#EFE8D6",
    ),
}


@cache
def font(path: str, weight: int) -> TTFont:
    f = TTFont(path)
    return instantiateVariableFont(f, {"wght": weight}) if "fvar" in f else f


def text_path(
    path: str, weight: int, text: str, size: float, x: float, y: float, tracking: float = 0.0, anchor: str = "start"
) -> str:
    """SVG path data for `text` with its baseline at y."""
    f = font(path, weight)
    scale = size / f["head"].unitsPerEm
    cmap, glyphs, hmtx = f.getBestCmap(), f.getGlyphSet(), f["hmtx"]
    names = [cmap.get(ord(ch), ".notdef") for ch in text]
    width = sum(hmtx[n][0] * scale + tracking for n in names) - tracking
    if anchor == "middle":
        x -= width / 2
    d, cursor = [], x
    for n in names:
        pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
        glyphs[n].draw(TransformPen(pen, (scale, 0, 0, -scale, cursor, y)))
        d.append(pen.getCommands())
        cursor += hmtx[n][0] * scale + tracking
    return " ".join(p for p in d if p)


def build(theme: str, sans: str, mono: str) -> str:
    c = THEMES[theme]
    sx = STATIONS[2][0]  # the quarantine branch leaves the line at silver
    branch = f"C{sx + 44} {TRACK_Y} {sx + 36} {Q_Y} {sx + 80} {Q_Y} H{Q_X}"
    reject_path = f"M{X0} {TRACK_Y} H{sx} {branch}"
    track = f"M{X0} {TRACK_Y} H{X1}"

    # Packets take each layer's colour as they pass its station (linear timing -> % of track length).
    def pct(x):
        return round((x - X0) / (X1 - X0) * 100, 2)

    b, s, g = (pct(st[0]) for st in STATIONS[1:])
    bm, sm, gm = (round(v - 0.01, 2) for v in (b, s, g))
    css = f"""
    .p {{ offset-path: path('{track}'); offset-rotate: 0deg; opacity: 0;
          animation: run 9s linear infinite, tint 9s linear infinite; }}
    .p2 {{ animation-delay: -3s; }} .p3 {{ animation-delay: -6s; }}
    .r {{ offset-path: path('{reject_path}'); offset-rotate: 0deg; opacity: 0;
          animation: reject 9s linear infinite; animation-delay: -1.5s; }}
    @keyframes run {{ 0% {{ offset-distance: 0%; opacity: 0 }} 4% {{ opacity: 1 }}
                      94% {{ opacity: 1 }} 100% {{ offset-distance: 100%; opacity: 0 }} }}
    @keyframes tint {{ 0%, {bm}% {{ fill: {c["muted"]} }} {b}%, {sm}% {{ fill: {c["bronze"]} }}
                       {s}%, {gm}% {{ fill: {c["silver"]} }} {g}%, 100% {{ fill: {c["gold"]} }} }}
    @keyframes reject {{ 0% {{ offset-distance: 0%; opacity: 0; fill: {c["muted"]} }}
                         4% {{ opacity: 1 }}
                         38% {{ fill: {c["bronze"]} }}
                         62% {{ fill: {c["reject"]} }}
                         72% {{ offset-distance: 100%; opacity: 1; fill: {c["reject"]} }}
                         86%, 100% {{ offset-distance: 100%; opacity: 0; fill: {c["reject"]} }} }}
    @media (prefers-reduced-motion: reduce) {{ .p, .r {{ animation: none; opacity: 0; }} }}
    """

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-labelledby="t d">',
        '<title id="t">Pawan Yandapalli, Data Engineer</title>',
        '<desc id="d">A data pipeline drawn as a line: records travel from landing through bronze, '
        "silver and gold; one record fails a check at silver and is routed to quarantine.</desc>",
        f"<style>{' '.join(css.split())}</style>",
        f'<rect width="{W}" height="{H}" fill="{c["bg"]}"/>',
        # headline
        f'<path fill="{c["ink"]}" d="{text_path(sans, 800, "Pawan Yandapalli", 64, 64, 120, -1.2)}"/>',
        f'<path fill="{c["ink"]}" d="{text_path(sans, 600, "Data Engineer", 28, 66, 166)}"/>',
        f'<path fill="{c["muted"]}" d="{text_path(sans, 500, TAGLINE, 19, 66, 200)}"/>',
        # track + quarantine branch
        f'<path d="{track}" stroke="{c["track"]}" stroke-opacity="0.28" stroke-width="2" fill="none"/>',
        f'<path d="M{sx} {TRACK_Y} {branch}" stroke="{c["reject"]}" stroke-opacity="0.55" stroke-width="2" '
        f'stroke-dasharray="4 5" fill="none"/>',
    ]
    for x, name, what, tone in STATIONS:
        ring = c[tone]
        parts += [
            f'<circle cx="{x}" cy="{TRACK_Y}" r="9" fill="{c["bg"]}" stroke="{ring}" stroke-width="3"/>',
            f'<circle cx="{x}" cy="{TRACK_Y}" r="3.5" fill="{ring}"/>',
            f'<path fill="{c["ink"]}" d="{text_path(mono, 700, name, 15, x, TRACK_Y - 44, 0, "middle")}"/>',
            f'<path fill="{c["muted"]}" d="{text_path(mono, 400, what, 12.5, x, TRACK_Y - 24, 0, "middle")}"/>',
        ]
    parts += [
        f'<circle cx="{Q_X}" cy="{Q_Y}" r="7" fill="{c["bg"]}" stroke="{c["reject"]}" stroke-width="2.5"/>',
        f'<path fill="{c["reject"]}" d="{text_path(mono, 700, "quarantine", 13.5, Q_X + 18, Q_Y + 5)}"/>',
        f'<path fill="{c["muted"]}" d="{text_path(mono, 400, Q_NOTE, 12.5, Q_X + 118, Q_Y + 5)}"/>',
        # end of line
        f'<path d="M{X1 - 8} {TRACK_Y - 6} L{X1} {TRACK_Y} L{X1 - 8} {TRACK_Y + 6}" stroke="{c["track"]}" '
        f'stroke-opacity="0.45" stroke-width="2" fill="none"/>',
        # moving records
        '<g><rect class="p p1" x="-6" y="-6" width="12" height="12" rx="2.5"/>'
        '<rect class="p p2" x="-6" y="-6" width="12" height="12" rx="2.5"/>'
        '<rect class="p p3" x="-6" y="-6" width="12" height="12" rx="2.5"/>'
        '<rect class="r" x="-6" y="-6" width="12" height="12" rx="2.5"/></g>',
        "</svg>",
    ]
    return "\n".join(parts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manrope", required=True)
    ap.add_argument("--mono", required=True)
    a = ap.parse_args()
    for theme in THEMES:
        (OUT / f"banner-{theme}.svg").write_text(build(theme, a.manrope, a.mono))
        print("wrote", OUT / f"banner-{theme}.svg")
