#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор технической инфографики
«Бортовая 4-лучевая АФАР S-диапазона Direct-to-Cell: взрыв-схема».

Рисунок строится программно в векторе (SVG 1920×1080, 16:9):
элементы задаются в 3D-координатах и проецируются косоугольной
проекцией «вид слева-спереди»; ось разнесения X горизонтальна,
ось глубины Z уходит вверх-влево.

    python3 generate.py            -> afar_exploded_view.svg
    node render.js                 -> afar_exploded_view.png (A3, ~300 dpi)
"""
import math
from pathlib import Path

from PIL import ImageFont

HERE = Path(__file__).resolve().parent
OUT_SVG = HERE / "afar_exploded_view.svg"

W, H = 1920, 1080
KX, KY = 0.55, 0.20          # проекция оси глубины Z: вверх-влево
AXIS_Y = 672                 # экранная высота оси разнесения

# --- цветовое кодирование соединений ------------------------------------
TX, TX_D, TX_L = "#d7263d", "#8a1222", "#ff9aa5"
RX, RX_D, RX_L = "#1f6fd6", "#0b3b80", "#9cc7ff"
PW, PW_D, PW_L = "#2f9e4f", "#17602c", "#97e3ad"
CT, CT_D, CT_L = "#f4b400", "#9c7300", "#ffe58a"
GR, GR_D = "#8c97a3", "#55606c"
NAVY = "#0b2a5b"
INK = "#14233c"
GREY_TXT = "#5d6a7b"
LEADER = "#7b8899"

FONT = "Inter, 'DejaVu Sans', Arial, sans-serif"
FONT_FILES = {
    "regular": "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
    "medium": "/usr/share/fonts/opentype/inter/Inter-Medium.otf",
    "semibold": "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
    "bold": "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
}
WEIGHT = {"regular": 400, "medium": 500, "semibold": 600, "bold": 700}
_font_cache = {}


def text_w(text, size, weight="regular"):
    key = (size, weight)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_FILES[weight], size)
    return _font_cache[key].getlength(text)


def wrap(text, size, width, weight="regular"):
    lines, cur = [], ""
    for word in text.split(" "):
        trial = word if not cur else cur + " " + word
        if text_w(trial, size, weight) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def pts(points):
    return " ".join(f"{f(x)},{f(y)}" for x, y in points)


def pd(points, close=False):
    s = "M" + " L".join(f"{f(x)},{f(y)}" for x, y in points)
    return s + (" Z" if close else "")


def text(x, y, s, size=12, weight="regular", fill=INK, anchor="start", extra=""):
    return (f'<text x="{f(x)}" y="{f(y)}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{WEIGHT[weight]}" fill="{fill}" text-anchor="{anchor}" {extra}>'
            f"{esc(s)}</text>")


def rect(x, y, w, h, fill, stroke="none", sw=0.6, rx=0, extra=""):
    return (f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="{f(rx)}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{f(sw)}" {extra}/>')


def circle(x, y, r, fill, stroke="none", sw=0.6, extra=""):
    return (f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{f(sw)}" {extra}/>')


def poly(points, fill, stroke="none", sw=0.6, extra=""):
    return (f'<polygon points="{pts(points)}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{f(sw)}" stroke-linejoin="round" {extra}/>')


def line(points, stroke, sw=1.0, extra=""):
    return (f'<path d="{pd(points)}" fill="none" stroke="{stroke}" stroke-width="{f(sw)}" '
            f'stroke-linecap="round" stroke-linejoin="round" {extra}/>')


# --- геометрия ломаных/кривых -----------------------------------------------
def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def rounded(wp, r=18, n=10):
    """Ломаная со скруглёнными углами (как уложенный кабель)."""
    out = [wp[0]]
    for i in range(1, len(wp) - 1):
        p0, p1, p2 = wp[i - 1], wp[i], wp[i + 1]
        d1, d2 = dist(p0, p1), dist(p1, p2)
        if d1 < 1e-6 or d2 < 1e-6:
            continue
        rr = min(r, d1 / 2, d2 / 2)
        a, b = lerp(p1, p0, rr / d1), lerp(p1, p2, rr / d2)
        out.append(a)
        for k in range(1, n):
            t = k / n
            q0, q1 = lerp(a, p1, t), lerp(p1, b, t)
            out.append(lerp(q0, q1, t))
        out.append(b)
    out.append(wp[-1])
    return out


def offset(points, d):
    res = []
    n = len(points)
    for i, p in enumerate(points):
        a = points[max(i - 1, 0)]
        b = points[min(i + 1, n - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        res.append((p[0] - dy / L * d, p[1] + dx / L * d))
    return res


def at_frac(points, frac):
    seg = [dist(points[i], points[i + 1]) for i in range(len(points) - 1)]
    total = sum(seg)
    target = total * frac
    acc = 0
    for i, s in enumerate(seg):
        if acc + s >= target and s > 0:
            t = (target - acc) / s
            p = lerp(points[i], points[i + 1], t)
            ang = math.atan2(points[i + 1][1] - points[i][1], points[i + 1][0] - points[i][0])
            return p, ang
        acc += s
    p = points[-1]
    return p, math.atan2(points[-1][1] - points[-2][1], points[-1][0] - points[-2][0])


def arrowhead(p, ang, size, fill, stroke):
    tip = (p[0] + math.cos(ang) * size * 0.6, p[1] + math.sin(ang) * size * 0.6)
    bl = (p[0] - math.cos(ang) * size * 0.6 + math.cos(ang + math.pi / 2) * size * 0.5,
          p[1] - math.sin(ang) * size * 0.6 + math.sin(ang + math.pi / 2) * size * 0.5)
    br = (p[0] - math.cos(ang) * size * 0.6 - math.cos(ang + math.pi / 2) * size * 0.5,
          p[1] - math.sin(ang) * size * 0.6 - math.sin(ang + math.pi / 2) * size * 0.5)
    return poly([tip, bl, br], fill, stroke, 0.6)


def cable(points, col, dark, light, w=2.6, arrows=(), reverse=False, arrow_size=None):
    """Коаксиальный кабель: тёмная обводка, тело, блик; стрелки — направление потока."""
    s = line(points, dark, w + 1.1)
    s += line(points, col, w)
    s += line(offset(points, -w * 0.22), light, max(w * 0.28, 0.5), 'stroke-opacity="0.85"')
    for fr in arrows:
        p, ang = at_frac(points, fr)
        if reverse:
            ang += math.pi
        s += arrowhead(p, ang, arrow_size or (w * 2.6 + 3), col, dark)
    return s


def ribbon(points, w, stripes=5):
    """Плоский шлейф (M-LVDS)."""
    a, b = offset(points, w / 2), offset(points, -w / 2)
    s = poly(a + b[::-1], CT, CT_D, 0.7)
    for k in range(1, stripes):
        s += line(offset(points, -w / 2 + w * k / stripes), CT_D, 0.35, 'stroke-opacity="0.7"')
    s += line(offset(points, -w * 0.3), CT_L, 0.6, 'stroke-opacity="0.9"')
    return s


def hull(points):
    pts_ = sorted(set((round(x, 3), round(y, 3)) for x, y in points))
    if len(pts_) <= 2:
        return pts_

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts_:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts_):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


# --- проекция ----------------------------------------------------------------
class Obj:
    """Локальная система координат элемента: x — вдоль оси разнесения,
    y — вверх, z — вглубь. Начало — на оси, в точке (ox, oy) экрана."""

    def __init__(self, ox, oy=AXIS_Y):
        self.ox, self.oy = ox, oy

    def P(self, x, y, z):
        return (self.ox + x - KX * z, self.oy - y - KY * z)

    def box(self, x, y, z, dx, dy, dz, left, top, front, stroke="#5b6774", sw=0.6, faces="ltf"):
        P = self.P
        L = [P(x, y, z), P(x, y, z + dz), P(x, y + dy, z + dz), P(x, y + dy, z)]
        T = [P(x, y + dy, z), P(x, y + dy, z + dz), P(x + dx, y + dy, z + dz), P(x + dx, y + dy, z)]
        F = [P(x, y, z), P(x + dx, y, z), P(x + dx, y + dy, z), P(x, y + dy, z)]
        s = ""
        for key, face, fill in (("l", L, left), ("t", T, top), ("f", F, front)):
            if key in faces:
                s += poly(face, fill, stroke, sw)
        return s

    # 2D-«холсты» на гранях: внутри можно рисовать в обычных координатах
    def left_canvas(self, x, ytop, zback):
        """Грань с нормалью −X: a — к переднему краю, b — вниз."""
        sx, sy = self.P(x, ytop, zback)
        return f"matrix({KX},{KY},0,1,{f(sx)},{f(sy)})"

    def front_canvas(self, x0, ytop, z):
        """Грань с нормалью −Z: без искажений."""
        sx, sy = self.P(x0, ytop, z)
        return f"translate({f(sx)},{f(sy)})"

    def top_canvas(self, x0, y, zback):
        """Грань с нормалью +Y: a — вдоль X, b — к зрителю."""
        sx, sy = self.P(x0, y, zback)
        return f"matrix(1,0,{KX},{KY},{f(sx)},{f(sy)})"

    def on_left(self, x, ytop, zback, a, b):
        sx, sy = self.P(x, ytop, zback)
        return (sx + KX * a, sy + KY * a + b)

    def cylinder(self, c, axis, r, length, side, cap, stroke="#55606c", n=40):
        """Цилиндр: c — центр основания, axis — единичный вектор оси."""
        ax = axis
        tmp = (0, 1, 0) if abs(ax[1]) < 0.9 else (1, 0, 0)
        u = (ax[1] * tmp[2] - ax[2] * tmp[1], ax[2] * tmp[0] - ax[0] * tmp[2], ax[0] * tmp[1] - ax[1] * tmp[0])
        Lu = math.sqrt(sum(v * v for v in u))
        u = tuple(v / Lu for v in u)
        v = (ax[1] * u[2] - ax[2] * u[1], ax[2] * u[0] - ax[0] * u[2], ax[0] * u[1] - ax[1] * u[0])
        ring0, ring1 = [], []
        for k in range(n):
            t = 2 * math.pi * k / n
            off = tuple(r * (math.cos(t) * u[i] + math.sin(t) * v[i]) for i in range(3))
            p0 = tuple(c[i] + off[i] for i in range(3))
            p1 = tuple(c[i] + off[i] + ax[i] * length for i in range(3))
            ring0.append(self.P(*p0))
            ring1.append(self.P(*p1))
        s = poly(hull(ring0 + ring1), side, stroke, 0.6)
        # видимый торец — тот, что ближе к камере (камера: −X, +Y, −Z)
        toward = -ax[0] + ax[1] * 0.4 - ax[2]
        s += poly(ring1 if toward > 0 else ring0, cap, stroke, 0.6)
        return s


# --- defs ------------------------------------------------------------------------
def lin(id_, stops, x1=0, y1=0, x2=1, y2=1, extra=""):
    st = "".join(f'<stop offset="{o}" stop-color="{c}"' + (f' stop-opacity="{a}"' if a is not None else "") + "/>"
                 for o, c, a in [(s + (None,))[:3] for s in stops])
    return f'<linearGradient id="{id_}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" {extra}>{st}</linearGradient>'


def defs():
    d = []
    d.append(lin("bg", [(0, "#ffffff"), (0.55, "#f3f8fd"), (1, "#dce9f7")], 0, 0, 1, 1))
    d.append('<radialGradient id="bgspot" cx="0.42" cy="0.55" r="0.65">'
             '<stop offset="0" stop-color="#ffffff" stop-opacity="0.9"/>'
             '<stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient>')
    # алюминий
    d.append(lin("alu_l", [(0, "#f6f8fb"), (0.5, "#dde3ea"), (1, "#bcc6d1")]))
    d.append(lin("alu_t", [(0, "#ffffff"), (1, "#e2e8ee")]))
    d.append(lin("alu_f", [(0, "#b9c3ce"), (1, "#8d99a6")], 0, 0, 1, 0))
    d.append(lin("alu_in", [(0, "#9aa6b3"), (1, "#c9d1da")], 0, 0, 1, 0))
    d.append(lin("alu_dk", [(0, "#a3aeba"), (1, "#7d8996")]))
    # тёмный корпус / платформа
    d.append(lin("plat_l", [(0, "#c5ccd4"), (1, "#9aa4af")]))
    d.append(lin("plat_t", [(0, "#e4e8ed"), (1, "#c9d0d8")]))
    d.append(lin("plat_f", [(0, "#8e99a5"), (1, "#6f7a86")], 0, 0, 1, 0))
    d.append(lin("rib", [(0, "#7a8591"), (0.45, "#d5dbe1"), (1, "#7f8a96")], 0, 0, 1, 0))
    # печатные платы
    d.append(lin("pcb", [(0, "#3a4756"), (1, "#1c252f")]))
    d.append(lin("pcb_edge", [(0, "#5a6878"), (1, "#3a4654")]))
    d.append(lin("sheen", [(0, "#ffffff", 0.22), (0.45, "#ffffff", 0.0), (1, "#ffffff", 0.06)]))
    # металлы
    d.append(lin("gold", [(0, "#fff0b8"), (0.45, "#e0b24a"), (1, "#a8761f")]))
    d.append(lin("gold_in", [(0, "#fff6d6"), (1, "#e7be5f")]))
    d.append(lin("copper", [(0, "#f6c29a"), (0.5, "#cf7a43"), (1, "#8e4520")]))
    d.append(lin("txpatch", [(0, "#ffd9c9"), (0.5, "#e98563"), (1, "#b2402c")]))
    d.append(lin("rxpatch", [(0, "#e1f0ff"), (0.5, "#79acea"), (1, "#3567b0")]))
    d.append(lin("chip", [(0, "#4a515b"), (1, "#14181d")]))
    d.append(lin("ceramic", [(0, "#ffffff"), (1, "#c7cbc6")]))
    d.append(lin("fin", [(0, "#eef1f4"), (1, "#a9b3be")], 0, 0, 1, 0))
    d.append(lin("dome", [(0, "#ffffff"), (1, "#c9d2dc")]))
    d.append(lin("lens", [(0, "#9fd3ff"), (0.6, "#1d4f8a"), (1, "#0c2547")]))
    d.append(lin("card", [(0, "#ffffff", 0.96), (1, "#f2f7fc", 0.94)], 0, 0, 0, 1))
    d.append(lin("panel", [(0, "#ffffff", 0.82), (1, "#eef5fc", 0.78)], 0, 0, 0, 1))
    chev = ["#4c97de", "#3a83cf", "#2a6cbb", "#1d56a0", "#103f80", "#0a2d61"]
    for i in range(5):
        d.append(lin(f"chev{i}", [(0, chev[i]), (1, chev[i + 1])], 0, 0, 1, 0))
    # соты
    s_ = 2.6
    hh = s_ * math.sqrt(3)
    d.append(f'<pattern id="hex" width="{f(3 * s_)}" height="{f(hh)}" patternUnits="userSpaceOnUse">'
             f'<path d="M0,{f(hh / 2)} L{f(s_ / 2)},0 L{f(1.5 * s_)},0 L{f(2 * s_)},{f(hh / 2)} '
             f'L{f(1.5 * s_)},{f(hh)} L{f(s_ / 2)},{f(hh)} Z M{f(2 * s_)},{f(hh / 2)} L{f(3 * s_)},{f(hh / 2)}" '
             f'fill="none" stroke="#7d8894" stroke-width="0.45"/></pattern>')
    # фильтры
    d.append('<filter id="shadow" x="-20%" y="-20%" width="150%" height="150%">'
             '<feGaussianBlur in="SourceAlpha" stdDeviation="5"/>'
             '<feOffset dx="5" dy="9" result="o"/>'
             '<feComponentTransfer><feFuncA type="linear" slope="0.22"/></feComponentTransfer>'
             '<feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    d.append('<filter id="cardshadow" x="-20%" y="-20%" width="140%" height="140%">'
             '<feGaussianBlur in="SourceAlpha" stdDeviation="6"/>'
             '<feOffset dx="0" dy="4" result="o"/>'
             '<feComponentTransfer><feFuncA type="linear" slope="0.16"/></feComponentTransfer>'
             '<feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    d.append('<filter id="glow" x="-50%" y="-50%" width="200%" height="200%">'
             '<feGaussianBlur in="SourceGraphic" stdDeviation="2.6" result="b"/>'
             '<feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    d.append('<filter id="floor" x="-50%" y="-200%" width="200%" height="500%">'
             '<feGaussianBlur stdDeviation="9"/></filter>')
    # элементы, повторяемые много раз
    d.append('<g id="patch">'
             '<rect x="-6.6" y="-6.6" width="13.2" height="13.2" fill="url(#gold)" stroke="#8a6116" stroke-width="0.5"/>'
             '<rect x="-4.2" y="-4.2" width="8.4" height="8.4" fill="url(#gold_in)" stroke="#a87a26" stroke-width="0.35"/>'
             '</g>')
    d.append('<g id="sma">'
             '<circle r="3.4" fill="url(#gold)" stroke="#7d5a14" stroke-width="0.5"/>'
             '<circle r="1.9" fill="#f3dc9a" stroke="#9a7420" stroke-width="0.4"/>'
             '<circle r="0.8" fill="#4a3a12"/></g>')
    return "<defs>" + "".join(d) + "</defs>"


# =================================================================================
# Слои
# =================================================================================
ANCHORS = {}   # точки для выносок


def floor_shadow(cx, w, y=938):
    return (f'<ellipse cx="{f(cx)}" cy="{f(y)}" rx="{f(w / 2)}" ry="7" fill="#0b2a5b" '
            f'fill-opacity="0.13" filter="url(#floor)"/>')



# --- раскладка слоёв вдоль оси с равными промежутками --------------------------
BR = dict(dx=50, dy=74, dz=36, pitch=46, z0=-96)
TW, TH, TD = 250, 300, 40
BD_T, BD_H, BD_D = 8, 262, 210
CB_T, CB_H, CB_D = 8, 180, 150
SD_T, SD_H, SD_D, SD_GAP = 10, 236, 150, 84
PS_DX, PS_DY, PS_DZ = 60, 118, 110
PL_DZ = 150
CARD_W = 150
_br_back = BR["z0"] + 5 * BR["pitch"] + BR["dz"]
FOOT = [  # (левый, правый) экранный вынос относительно ox
    (6 - KX * 177, 28 + KX * 177),
    (0, CARD_W),
    (-KX * _br_back, BR["dx"] - KX * BR["z0"]),
    (-KX * TD, TW),
    (-KX * BD_D / 2, BD_T + KX * BD_D / 2),
    (-KX * BD_D / 2, BD_T + KX * BD_D / 2),
    (-KX * CB_D / 2, CB_T + KX * CB_D / 2),
    (-KX * SD_D / 2, SD_GAP + SD_T + KX * SD_D / 2),
    (-KX * PS_DZ / 2 - 8, PS_DX + KX * PS_DZ / 2),
    (-KX * PL_DZ / 2, 0),
]
X_START, X_PLAT = 34, 1716
GAP = (X_PLAT - X_START - sum(r - l for l, r in FOOT[:9])) / 9
OX = []
_x = X_START
for l, r in FOOT:
    OX.append(_x - l)
    _x += (r - l) + GAP

# 1. Антенное полотно --------------------------------------------------------------
ANT = Obj(OX[0])
ANT_D, ANT_H = 330, 400          # 1,0 м (глубина, 18 АЭ) × 1,2 м (высота, 22 АЭ)
PA, PB = ANT_D / 18, ANT_H / 22
SUB_I, SUB_J = 11, 8             # подрешётка 2×2, выделенная рамкой


def layer_antenna():
    o = ANT
    s = ""
    # сотовое основание
    s += o.box(6, -212, -177, 22, 424, 354, "url(#alu_l)", "url(#alu_t)", "url(#alu_f)")
    s += f'<g transform="{o.front_canvas(6, 212, -177)}"><rect width="22" height="424" fill="url(#hex)" opacity="0.8"/></g>'
    s += f'<g transform="{o.top_canvas(6, 212, 177)}"><rect width="22" height="354" fill="url(#hex)" opacity="0.7"/></g>'
    # крепёжные бобышки по углам основания
    for (a, b) in ((6, 6), (348, 6), (6, 418), (348, 418)):
        p = o.on_left(6, 212, 177, a, b)
        s += f'<ellipse cx="{f(p[0])}" cy="{f(p[1])}" rx="2.4" ry="3.2" fill="#9aa5b1" stroke="#5f6b78" stroke-width="0.4"/>'
    # излучающая плата
    s += o.box(0, -200, -165, 6, 400, 330, "#2a3440", "url(#pcb_edge)", "#2b3541", faces="tf")
    g = f'<g transform="{o.left_canvas(0, 200, 165)}">'
    g += rect(0, 0, ANT_D, ANT_H, "url(#pcb)", "#151c24", 0.8)
    for i in range(18):
        for j in range(22):
            g += f'<use href="#patch" x="{f(PA * (i + 0.5))}" y="{f(PB * (j + 0.5))}"/>'
    # выделенная подрешётка 2×2
    x0, y0 = PA * SUB_I + 0.8, PB * SUB_J + 0.8
    g += rect(x0, y0, 2 * PA - 1.6, 2 * PB - 1.6, "none", "#3fe0ff", 2.4, 2, 'filter="url(#glow)"')
    g += rect(x0, y0, 2 * PA - 1.6, 2 * PB - 1.6, "none", "#ffffff", 0.9, 2)
    g += rect(0, 0, ANT_D, ANT_H, "url(#sheen)")
    g += "</g>"
    s += g
    ANCHORS[1] = o.on_left(0, 200, 165, 60, 30)
    ANCHORS["sub_tl"] = o.on_left(0, 200, 165, x0, y0)
    ANCHORS["sub_br"] = o.on_left(0, 200, 165, x0 + 2 * PA, y0 + 2 * PB)
    return f'<g filter="url(#shadow)">{s}</g>'


# 2. Врезка подрешётки 2×2 в разрезе ------------------------------------------------
CARD2 = (OX[1], 540, CARD_W, 272)
ISO_C = (OX[1] + 78, 708)
HS = 32                      # половина размера подрешётки 2×2


def Q(u, w, h):
    cx, cy = ISO_C
    return (cx + (u - w) * 0.78, cy + (u + w) * 0.33 - h)


def iso_plate(h0, t, top_fill, side_l, side_r, stroke="#5b6774"):
    s = poly([Q(-HS, -HS, h0 + t), Q(HS, -HS, h0 + t), Q(HS, HS, h0 + t), Q(-HS, HS, h0 + t)], top_fill, stroke, 0.6)
    s += poly([Q(HS, -HS, h0 + t), Q(HS, HS, h0 + t), Q(HS, HS, h0), Q(HS, -HS, h0)], side_r, stroke, 0.6)
    s += poly([Q(-HS, HS, h0 + t), Q(HS, HS, h0 + t), Q(HS, HS, h0), Q(-HS, HS, h0)], side_l, stroke, 0.6)
    return s


def iso_patch(cu, cw, h, half, fill, stroke):
    return poly([Q(cu - half, cw - half, h), Q(cu + half, cw - half, h),
                 Q(cu + half, cw + half, h), Q(cu - half, cw + half, h)], fill, stroke, 0.5)


CELLS = [(-15, -15), (15, -15), (-15, 15), (15, 15)]
H_BASE, H_RX, H_TX = (0, 10), 62, 114
PORTS2 = []


def layer_inset_subarray():
    x, y, w, h = CARD2
    s = rect(x, y, w, h, "url(#card)", "#b3c3d4", 1, 10, 'filter="url(#cardshadow)"')
    s += text(x + 10, y + 18, "ВРЕЗКА · РАЗРЕЗ", 9, "semibold", "#7a8899", extra='letter-spacing="0.6"')
    # основание (соты)
    s += iso_plate(0, 10, "#cfd6de", "#a9b3be", "#bcc5cf")
    s += f'<g opacity="0.55">{poly([Q(-HS, HS, 10), Q(HS, HS, 10), Q(HS, HS, 0), Q(-HS, HS, 0)], "url(#hex)")}</g>'
    # порты под основанием и штыри питания
    pins_lo, pins_hi = "", ""
    PORTS2.clear()
    for (cu, cw) in CELLS:
        for du, col, dk in ((-6, RX, RX_D), (6, TX, TX_D)):
            u = cu + du
            top = H_RX if col == RX else H_TX
            p_bot = Q(u, cw, 0)
            p_top = Q(u, cw, top)
            pins_lo += line([p_bot, Q(u, cw, min(top, H_RX))], col, 1.3)
            if col == TX:
                pins_hi += line([Q(u, cw, H_RX + 3), p_top], col, 1.3)
            PORTS2.append((Q(u, cw, -9), col, dk))
    s += pins_lo
    # Rx-слой
    s += iso_plate(H_RX - 3, 3, "#e9eef3", "#c4ccd5", "#d6dde4")
    for (cu, cw) in CELLS:
        s += iso_patch(cu, cw, H_RX, 11, "url(#rxpatch)", RX_D)
        s += f'<ellipse cx="{f(Q(cu - 6, cw, H_RX)[0])}" cy="{f(Q(cu - 6, cw, H_RX)[1])}" rx="1.6" ry="1" fill="{RX_D}"/>'
    s += pins_hi
    # Tx-слой
    s += iso_plate(H_TX - 3, 3, "#f1f3f6", "#cdd3da", "#dde2e8")
    for (cu, cw) in CELLS:
        s += iso_patch(cu, cw, H_TX, 8, "url(#txpatch)", TX_D)
        s += f'<ellipse cx="{f(Q(cu + 6, cw, H_TX)[0])}" cy="{f(Q(cu + 6, cw, H_TX)[1])}" rx="1.6" ry="1" fill="{TX_D}"/>'
    # SMA-порты (по два на АЭ)
    for (p, col, dk) in sorted(PORTS2, key=lambda t: t[0][1]):
        s += rect(p[0] - 2.2, p[1] - 9, 4.4, 9, "url(#gold)", "#7d5a14", 0.4)
        s += f'<ellipse cx="{f(p[0])}" cy="{f(p[1] - 5)}" rx="2.6" ry="1.2" fill="{col}"/>'
        s += f'<ellipse cx="{f(p[0])}" cy="{f(p[1])}" rx="2.2" ry="1" fill="#d9b55a" stroke="#7d5a14" stroke-width="0.4"/>'
    # подписи слоёв
    lx = x + 9
    s += text(lx, Q(-HS, HS, H_TX)[1] - 11, "Tx-слой", 10, "bold", TX)
    s += text(lx, Q(-HS, HS, H_RX)[1] - 11, "Rx-слой", 10, "bold", RX)
    s += text(lx, Q(-HS, HS, 10)[1] - 17, "основание", 8.5, "semibold", "#6c7886")
    ANCHORS[2] = (x + w / 2, y)
    return s


# 3. Ряд ППМ ---------------------------------------------------------------------------
PPM = Obj(OX[2])


def brick(o, z0, ghost=False, front_label=False):
    dx, dy, dz = BR["dx"], BR["dy"], BR["dz"]
    y0 = -dy / 2
    if ghost:
        return o.box(0, y0, z0, dx, dy, dz, "#ffffff", "#ffffff", "#ffffff", "#9aa6b3", 0.8).replace(
            'fill="#ffffff"', 'fill="#ffffff" fill-opacity="0.35" stroke-dasharray="3 2"')
    s = o.box(0, y0, z0, dx, dy, dz, "url(#alu_l)", "url(#alu_t)", "url(#alu_f)", "#5f6b78", 0.7)
    # фрезерованный карман на крышке
    s += f'<g transform="{o.top_canvas(0, dy / 2, z0 + dz)}">'
    s += rect(5, 4, dx - 10, dz - 8, "#d5dce4", "#9aa5b1", 0.5, 3)
    for (a, b) in ((2.6, 2.4), (dx - 2.6, 2.4), (2.6, dz - 2.4), (dx - 2.6, dz - 2.4)):
        s += circle(a, b, 1.1, "#8a96a3")
    s += "</g>"
    # 8 ВЧ-разъёмов к антенне на левой грани
    g = f'<g transform="{o.left_canvas(0, dy / 2, z0 + dz)}">'
    for k in range(8):
        g += f'<use href="#sma" x="{f(dz / 2)}" y="{f(7 + k * 7.4)}" transform="scale(1)"/>'
    g += "</g>"
    s += g
    if front_label:
        s += f'<g transform="{o.front_canvas(0, dy / 2, z0)}">'
        s += text(dx / 2, dy / 2 - 3, "ППМ", 10, "bold", "#3b4654", "middle")
        s += text(dx / 2, dy / 2 + 9, "№1", 8, "medium", "#4d5966", "middle")
        s += "</g>"
    return s


def ppm_connectors():
    """Экранные координаты 8 разъёмов на левой грани переднего ППМ (сверху вниз)."""
    dz, dy, z0 = BR["dz"], BR["dy"], BR["z0"]
    return [PPM.on_left(0, dy / 2, z0 + dz, dz / 2, 7 + k * 7.4) for k in range(8)]


def layer_ppm_row():
    o = PPM
    s = ""
    n_solid, n_ghost = 4, 2
    for k in reversed(range(n_solid + n_ghost)):
        z0 = BR["z0"] + k * BR["pitch"]
        s += brick(o, z0, ghost=k >= n_solid, front_label=(k == 0))
    p = o.P(0, BR["dy"] / 2, BR["z0"] + (n_solid + n_ghost - 1) * BR["pitch"] + BR["dz"])
    s += text(p[0] + 2, p[1] - 10, "…×99", 18, "bold", "#3b4654")
    ANCHORS[3] = o.P(BR["dx"] / 2, BR["dy"] / 2, BR["z0"] + 2 * BR["pitch"] + BR["dz"] / 2)
    ANCHORS["ppm_front_tl"] = o.P(BR["dx"], BR["dy"] / 2, BR["z0"])
    ANCHORS["ppm_front_bl"] = o.P(BR["dx"], -BR["dy"] / 2, BR["z0"])
    return f'<g filter="url(#shadow)">{s}</g>'


# 4. ППМ со снятой крышкой (врезка-увеличение) --------------------------------------
TRAY = Obj(OX[3])


def chip(x, y, w, h, label=None, mark=None, size=7.5, sub=None, sub_col=None):
    s = rect(x + 1.2, y + 1.6, w, h, "#000000", extra='fill-opacity="0.35"', rx=1.5)
    s += rect(x, y, w, h, "url(#chip)", "#0b0e12", 0.6, 1.5)
    s += rect(x + 1.5, y + 1.5, w - 3, h * 0.35, "#ffffff", extra='fill-opacity="0.06"', rx=1)
    if mark:
        s += circle(x + 3.2, y + 3.2, 1.2, mark)
    if label:
        s += text(x + w / 2, y + h / 2 + (size * 0.35 if not sub else -1), label, size, "bold", mark or "#e8ecf0", "middle")
    if sub:
        s += text(x + w / 2, y + h / 2 + size * 0.95, sub, size * 0.82, "medium", sub_col or "#c9d1d9", "middle")
    return s


def layer_open_ppm():
    o = TRAY
    s = ""
    # плата на дне корпуса
    bw, bh = TW - 12, TH - 12
    g = f'<g transform="{o.front_canvas(6, TH / 2 - 6, TD)}">'
    g += rect(0, 0, bw, bh, "url(#pcb)", "#151c24", 0.8)
    # крепёжные отверстия
    for (a, b) in ((30, 10), (bw - 10, 10), (30, bh - 10), (bw - 10, bh - 10)):
        g += circle(a, b, 3, "#c9a24a", "#7d5a14", 0.5) + circle(a, b, 1.4, "#1a2027")
    tx_rows = [30, 58, 86, 114]
    rx_rows = [178, 206, 234, 262]
    # ВЧ-тракты TX (сеть -> Core-Chip Tx -> УМ -> ППФ -> антенна)
    for k, b in enumerate(tx_rows):
        bc = 52 + k * 12
        g += line([(bw - 4, b), (bw - 26, b), (bw - 40, bc), (186, bc)], TX, 1.5)
        g += line([(128, bc), (118, bc), (112, b), (105, b)], TX, 1.5)
        g += line([(79, b), (62, b)], TX, 1.5)
        g += line([(32, b), (24, b)], TX, 1.5)
        g += arrowhead((70.5, b), math.pi, 5.5, TX, TX_D)
    for k, b in enumerate(rx_rows):
        bc = 200 + k * 12
        g += line([(24, b), (32, b)], RX, 1.5)
        g += line([(62, b), (80, b)], RX, 1.5)
        g += line([(104, b), (112, b), (118, bc), (128, bc)], RX, 1.5)
        g += line([(186, bc), (bw - 40, bc), (bw - 26, b), (bw - 4, b)], RX, 1.5)
        g += arrowhead((71, b), 0, 5.5, RX, RX_D)
    # управление (жёлтые) и питание (зелёные)
    g += line([(bw - 4, 138), (176, 138)], CT, 1.4)
    g += line([(bw - 4, 146), (176, 146)], CT, 1.4)
    g += line([(150, 124), (150, 100)], CT, 1.4)
    g += line([(158, 124), (158, 100)], CT, 1.4)
    g += line([(150, 166), (150, 192)], CT, 1.4)
    g += line([(158, 166), (158, 192)], CT, 1.4)
    g += line([(bw - 4, 156), (214, 156)], PW, 1.6)
    g += line([(199, 128), (199, 10), (92, 10), (92, 16)], PW, 1.4, 'stroke-dasharray="4 2"')
    g += line([(199, 166), (199, 282), (92, 282), (92, 268)], PW, 1.4, 'stroke-dasharray="4 2"')
    # ППФ (керамика)
    for b in tx_rows + rx_rows:
        g += rect(33, b - 7.5, 29, 15, "url(#ceramic)", "#8f9690", 0.6, 1.5)
        g += rect(33, b - 7.5, 4, 15, "#d7dbe0", "#8f9690", 0.4)
        g += rect(58, b - 7.5, 4, 15, "#d7dbe0", "#8f9690", 0.4)
    g += text(47.5, 20, "ППФ Tx", 6.5, "semibold", "#d7dde3", "middle")
    g += text(47.5, rx_rows[-1] + 17, "ППФ Rx", 6.5, "semibold", "#d7dde3", "middle")
    # медный теплоотвод + 4 GaN УМ
    g += rect(70, 15, 44, 114, "url(#copper)", "#7a3a18", 0.7, 2)
    for b in tx_rows:
        g += chip(79, b - 8, 26, 16, "GaN", TX, 6.5)
    g += text(92, 140, "УМ GaN", 6.5, "semibold", "#d7dde3", "middle")
    # 4 GaAs МШУ
    for b in rx_rows:
        g += chip(80, b - 7, 24, 14, "МШУ", RX_L, 6)
    g += text(92, 170, "МШУ GaAs", 6.5, "semibold", "#d7dde3", "middle")
    # Core-Chip Tx/Rx
    g += chip(128, 42, 58, 58, "Core-Chip Tx", TX, 7, "ФВ·АТТ ×4", "#ffb3bb")
    g += chip(128, 190, 58, 58, "Core-Chip Rx", RX, 7, "ФВ·АТТ ×4", "#b8d6ff")
    # ПЛИС/CPLD и PMIC
    g += chip(128, 124, 50, 42, "CPLD", CT, 8, "ПЛИС", CT_L)
    g += chip(184, 129, 30, 33, "PMIC", PW_L, 6.5)
    # разъём питания/управления
    g += rect(bw - 18, 132, 14, 30, "#cfd5dc", "#59636e", 0.6, 1.5)
    for k in range(4):
        g += circle(bw - 11, 137 + k * 6.5, 1.3, CT if k < 2 else (PW if k == 3 else CT))
    # контактные площадки разъёмов
    for b in tx_rows + rx_rows:
        g += rect(20, b - 3, 6, 6, "url(#gold)", "#7d5a14", 0.4)
        g += rect(bw - 7, b - 3, 6, 6, "url(#gold)", "#7d5a14", 0.4)
    g += rect(0, 0, bw, bh, "url(#sheen)")
    g += "</g>"
    s += g
    # стенки корпуса (фрезерованный алюминий)
    s += o.box(TW - 6, -TH / 2 + 6, 0, 6, TH - 12, TD, "url(#alu_in)", "url(#alu_t)", "url(#alu_f)", "#5f6b78", 0.6)
    s += o.box(6, -TH / 2, 0, TW - 12, 6, TD, "url(#alu_l)", "url(#alu_in)", "url(#alu_f)", "#5f6b78", 0.6)
    s += o.box(6, TH / 2 - 6, 0, TW - 12, 6, TD, "url(#alu_l)", "url(#alu_t)", "url(#alu_f)", "#5f6b78", 0.6)
    s += o.box(0, -TH / 2, 0, 6, TH, TD, "url(#alu_l)", "url(#alu_t)", "url(#alu_f)", "#5f6b78", 0.6)
    # ВЧ-разъёмы на стенке со стороны антенны
    g = f'<g transform="{o.left_canvas(0, TH / 2, TD)}">'
    for k, b in enumerate([30, 58, 86, 114, 178, 206, 234, 262]):
        g += f'<use href="#sma" x="{f(TD / 2)}" y="{f(b + 6)}"/>'
    g += "</g>"
    s += g
    # винты по углам
    for (x, y) in ((3, TH / 2 - 3), (TW - 3, TH / 2 - 3)):
        p = o.P(x, y, TD / 2)
        s += f'<ellipse cx="{f(p[0])}" cy="{f(p[1])}" rx="2" ry="1" fill="#8a96a3"/>'
    ANCHORS[4] = o.P(TW * 0.42, TH / 2, TD)
    ANCHORS["tray_tl"] = o.P(0, TH / 2, TD)
    ANCHORS["tray_bl"] = o.P(0, -TH / 2, 0)
    return f'<g filter="url(#shadow)">{s}</g>'


# 5/6. Платы TX-распределения и RX-комбинирования ------------------------------------
TXB = Obj(OX[4])
RXB = Obj(OX[5])


def wilkinson_tree(cx, b0, levels, spread, step, col, dark):
    """Дерево делителей Вилкинсона, ветвящееся вниз (b растёт)."""
    s = ""
    nodes = [cx]
    b = b0
    ends = []
    for lev in range(levels):
        nb = b + step
        new = []
        half = spread / (2 ** (lev + 1))
        for x in nodes:
            xl, xr = x - half, x + half
            # кольцо Вилкинсона и балластный резистор
            s += f'<path d="M{f(x)},{f(b)} C{f(x - half * 0.9)},{f(b + 2)} {f(xl)},{f(b + step * 0.3)} {f(xl)},{f(b + step * 0.55)}" fill="none" stroke="{col}" stroke-width="1.5"/>'
            s += f'<path d="M{f(x)},{f(b)} C{f(x + half * 0.9)},{f(b + 2)} {f(xr)},{f(b + step * 0.3)} {f(xr)},{f(b + step * 0.55)}" fill="none" stroke="{col}" stroke-width="1.5"/>'
            s += rect(x - 2.2, b + step * 0.38, 4.4, 2.6, "#1a1a1a", "#c9ced4", 0.4)
            s += line([(xl, b + step * 0.55), (xl, nb)], col, 1.5)
            s += line([(xr, b + step * 0.55), (xr, nb)], col, 1.5)
            s += circle(x, b, 1.6, dark)
            new += [xl, xr]
        nodes = new
        b = nb
    for x in nodes:
        ends.append((x, b))
    return s, ends


def board_frame(o):
    s = o.box(0, -BD_H / 2, -BD_D / 2, BD_T, BD_H, BD_D, "#2a3440", "url(#pcb_edge)", "#2b3541", faces="tf")
    return s


def layer_tx_board():
    o = TXB
    s = board_frame(o)
    g = f'<g transform="{o.left_canvas(0, BD_H / 2, BD_D / 2)}">'
    g += rect(0, 0, BD_D, BD_H, "url(#pcb)", "#151c24", 0.8)
    for k in range(4):
        cx = BD_D / 8 + k * BD_D / 4
        g += f'<use href="#sma" x="{f(cx)}" y="7"/>'
        g += line([(cx, 10), (cx, 22)], TX, 1.6)
        g += chip(cx - 13, 22, 26, 22, "ДР", TX, 8)
        g += line([(cx, 44), (cx, 56)], TX, 1.6)
        t, ends = wilkinson_tree(cx, 56, 3, 28, 30, TX, TX_D)
        g += t
        for (x, b) in ends:
            g += line([(x, b), (x, 236)], TX, 1.1)
        g += text(cx, 160, "1:99", 8, "bold", "#ffb3bb", "middle")
    # выходной разъёмный ряд
    g += rect(8, 234, BD_D - 16, 20, "#cfd5dc", "#59636e", 0.6, 2)
    for k in range(25):
        g += circle(14 + k * 7.6, 244, 2.1, "url(#gold)", "#7d5a14", 0.35)
    g += text(BD_D / 2, 228, "→ 4 × 99 выходов к ППМ", 7.5, "semibold", "#d9dfe5", "middle")
    g += rect(0, 0, BD_D, BD_H, "url(#sheen)")
    g += "</g>"
    s += g
    ANCHORS[5] = o.on_left(0, BD_H / 2, BD_D / 2, 30, 0)
    return f'<g filter="url(#shadow)">{s}</g>'


def layer_rx_board():
    o = RXB
    s = board_frame(o)
    g = f'<g transform="{o.left_canvas(0, BD_H / 2, BD_D / 2)}">'
    g += rect(0, 0, BD_D, BD_H, "url(#pcb)", "#151c24", 0.8)
    for k in range(4):
        cx = BD_D / 8 + k * BD_D / 4
        g += f'<use href="#sma" x="{f(cx)}" y="7"/>'
        g += line([(cx, 10), (cx, 22)], RX, 1.6)
        g += chip(cx - 13, 22, 26, 22, "МШУ", RX_L, 7)
        g += line([(cx, 44), (cx, 56)], RX, 1.6)
        t, ends = wilkinson_tree(cx, 56, 3, 28, 30, RX, RX_D)
        g += t
        for (x, b) in ends:
            g += line([(x, b), (x, 236)], RX, 1.1)
        g += text(cx, 160, "99:1", 8, "bold", "#b8d6ff", "middle")
    g += rect(8, 234, BD_D - 16, 20, "#cfd5dc", "#59636e", 0.6, 2)
    for k in range(25):
        g += circle(14 + k * 7.6, 244, 2.1, "url(#gold)", "#7d5a14", 0.35)
    g += text(BD_D / 2, 228, "← 4 × 99 входов от ППМ", 7.5, "semibold", "#d9dfe5", "middle")
    g += rect(0, 0, BD_D, BD_H, "url(#sheen)")
    g += "</g>"
    s += g
    ANCHORS[6] = o.on_left(0, BD_H / 2, BD_D / 2, 30, 0)
    return f'<g filter="url(#shadow)">{s}</g>'


def board_top_points(o, n=4):
    """Входные разъёмы на верхнем крае платы (экран)."""
    return [o.on_left(0, BD_H / 2, BD_D / 2, BD_D / 8 + k * BD_D / 4, 7) for k in range(n)]


def board_bottom_points(o, n=6):
    return [o.on_left(0, BD_H / 2, BD_D / 2, 30 + k * 32, 250) for k in range(n)]


# 7. Плата управления (M-LVDS) ---------------------------------------------------------
CTL = Obj(OX[6])


def layer_ctl_board():
    o = CTL
    s = o.box(0, -CB_H / 2, -CB_D / 2, CB_T, CB_H, CB_D, "#2a3440", "url(#pcb_edge)", "#2b3541", faces="tf")
    g = f'<g transform="{o.left_canvas(0, CB_H / 2, CB_D / 2)}">'
    g += rect(0, 0, CB_D, CB_H, "url(#pcb)", "#151c24", 0.8)
    for k in range(4):
        cx = 24 + k * 34
        g += line([(cx, 18), (cx, 44)], CT, 1.4)
        g += line([(cx, 80), (cx, 150)], CT, 1.4)
        g += chip(cx - 14, 44, 28, 36, "DS91M", CT, 6.2, "124", CT_L)
    g += line([(10, 18), (140, 18)], CT, 1.4)
    g += rect(8, 8, 26, 9, "#cfd5dc", "#59636e", 0.5, 1)
    g += text(21, 15, "SPI", 5.5, "bold", "#3b4654", "middle")
    g += line([(12, 100), (140, 100)], CT, 1.0, 'stroke-dasharray="3 2"')
    g += text(75, 96, "LOAD", 7, "bold", CT_L, "middle")
    g += rect(6, 150, CB_D - 12, 22, "#cfd5dc", "#59636e", 0.6, 2)
    for k in range(4):
        g += rect(12 + k * 34, 155, 26, 12, "#2f3640", "#59636e", 0.4, 1)
    g += rect(0, 0, CB_D, CB_H, "url(#sheen)")
    g += "</g>"
    s += g
    ANCHORS[7] = o.on_left(0, CB_H / 2, CB_D / 2, 30, 0)
    return f'<g filter="url(#shadow)">{s}</g>'


# 8. Два модуля SDR ----------------------------------------------------------------
SDR = Obj(OX[7])


def sdr_board(o, x, num):
    s = o.box(x, -SD_H / 2, -SD_D / 2, SD_T, SD_H, SD_D, "#2a3440", "url(#alu_t)", "url(#alu_f)", "#5f6b78", 0.6, faces="tf")
    g = f'<g transform="{o.left_canvas(x, SD_H / 2, SD_D / 2)}">'
    g += rect(0, 0, SD_D, SD_H, "url(#alu_dk)", "#5f6b78", 0.8)
    g += rect(5, 5, SD_D - 10, SD_H - 10, "url(#pcb)", "#151c24", 0.6)
    g += text(SD_D / 2, 18, f"SDR TREVO №{num}", 9, "bold", "#e6ebf0", "middle")
    g += chip(22, 28, 106, 62, "FPGA", "#e9eef3", 17, "4 IQ · Доплер", "#c3ccd6")
    g += chip(22, 100, 106, 62, "RFSoC", "#e9eef3", 17, "ЦАП / АЦП", "#c3ccd6")
    g += chip(40, 172, 70, 42, "ARM", "#e9eef3", 15)
    for k in range(4):
        g += line([(8, 44 + k * 10), (22, 44 + k * 10)], TX, 1.4)
        g += line([(8, 118 + k * 10), (22, 118 + k * 10)], RX, 1.4)
    g += line([(75, 90), (75, 100)], CT, 1.6)
    g += line([(75, 162), (75, 172)], CT, 1.6)
    g += rect(0, 0, SD_D, SD_H, "url(#sheen)")
    g += "</g>"
    s += g
    return s


def sdr_left_points(kind):
    """Точки входа лучей на лицевую грань модуля №1 (экран)."""
    if kind == "tx":
        return [SDR.on_left(0, SD_H / 2, SD_D / 2, 8, 44 + k * 10) for k in range(4)]
    return [SDR.on_left(0, SD_H / 2, SD_D / 2, 8, 118 + k * 10) for k in range(4)]


def layer_sdr():
    s = sdr_board(SDR, SD_GAP, 2) + sdr_board(SDR, 0, 1)
    ANCHORS[8] = SDR.on_left(0, SD_H / 2, SD_D / 2, 20, 0)
    return f'<g filter="url(#shadow)">{s}</g>'


# 9. Силовой модуль (ВИП) ----------------------------------------------------------
PSU = Obj(OX[8])


def layer_psu():
    o = PSU
    s = ""
    dx, dy, dz = PS_DX, PS_DY, PS_DZ
    y0 = -dy / 2 - 10
    s += o.box(0, y0, -dz / 2, dx, dy, dz, "url(#alu_l)", "url(#alu_t)", "url(#alu_f)", "#5f6b78", 0.7)
    # радиатор: рёбра на крышке
    fins = ""
    for k in reversed(range(11)):
        x = 3 + k * 5.2
        fins += o.box(x, y0 + dy, -dz / 2 + 4, 1.8, 30, dz - 8, "url(#fin)", "#ffffff", "#a9b3be", "#7d8894", 0.35)
    s += fins
    # тепловые трубки
    for k, zz in enumerate((-30, -10, 10, 30)):
        p0 = o.P(-2, y0 + dy - 20, zz)
        p1 = o.P(-8, y0 + dy + 4, zz)
        p2 = o.P(4 + k * 12, y0 + dy + 18, zz)
        pts_ = rounded([p0, p1, p2], 10)
        s += line(pts_, "#7a3a18", 4.2) + line(pts_, "url(#copper)", 3.0) + line(offset(pts_, -0.8), "#ffd2b0", 0.8)
    # лицевая панель с разъёмами
    g = f'<g transform="{o.left_canvas(0, y0 + dy, dz / 2)}">'
    g += rect(8, 10, dz - 16, 34, "#2f3a46", "#1b232c", 0.6, 3)
    g += text(dz / 2, 25, "ВИП", 11, "bold", "#e9eef3", "middle")
    g += text(dz / 2, 38, "100 → 27 В", 8, "semibold", PW_L, "middle")
    for k, b in enumerate((62, 86)):
        g += circle(30, b, 7, "#cfd5dc", "#59636e", 0.6) + circle(30, b, 4, PW, PW_D, 0.6)
        g += text(46, b + 3, f"27 В · шина {k + 1}", 7.5, "semibold", "#2b3541")
    g += circle(30, 108, 6, "#cfd5dc", "#59636e", 0.6) + circle(30, 108, 3.5, PW_D)
    g += text(46, 111, "100 В", 7.5, "semibold", "#2b3541")
    g += "</g>"
    s += g
    ANCHORS[9] = o.P(30, y0 + dy + 30, 0)
    ANCHORS["psu_out1"] = o.on_left(0, y0 + dy, dz / 2, 30, 62)
    ANCHORS["psu_out2"] = o.on_left(0, y0 + dy, dz / 2, 30, 86)
    ANCHORS["psu_in"] = o.on_left(0, y0 + dy, dz / 2, 30, 108)
    return f'<g filter="url(#shadow)">{s}</g>'


# 10. Фрагмент спутниковой платформы -----------------------------------------------
PLAT = Obj(OX[9])


def layer_platform():
    o = PLAT
    s = ""
    dx, dy, dz = 200, 330, PL_DZ
    y0 = -dy / 2
    s += o.box(0, y0, -dz / 2, dx, dy, dz, "url(#plat_l)", "url(#plat_t)", "url(#plat_f)", "#4f5a66", 0.8)
    # рёбра радиатора на передней грани
    g = f'<g transform="{o.front_canvas(0, dy / 2, -dz / 2)}">'
    for k in range(17):
        g += rect(10 + k * 10.5, 14, 6, dy - 28, "url(#rib)", "#5f6b78", 0.35, 1)
    g += "</g>"
    s += g
    # монтажный интерфейс на грани, обращённой к стеку
    g = f'<g transform="{o.left_canvas(0, dy / 2, dz / 2)}">'
    g += rect(14, 40, dz - 28, dy - 80, "#d9dee4", "#7d8894", 0.7, 4)
    for a in (24, dz - 24):
        for b in (52, 120, 190, 260):
            g += circle(a, b, 3.2, "#9aa5b1", "#5f6b78", 0.5) + circle(a, b, 1.2, "#4f5a66")
    g += circle(dz / 2, 150, 8, "#cfd5dc", "#59636e", 0.6) + circle(dz / 2, 150, 4.5, PW, PW_D, 0.6)
    g += text(dz / 2, 172, "100 В", 8, "bold", PW_D, "middle")
    g += rect(dz / 2 - 14, 196, 28, 14, "#2f3640", "#59636e", 0.5, 2)
    g += text(dz / 2, 222, "PPS · ISL", 7, "bold", CT_D, "middle")
    g += "</g>"
    s += g
    top = dy / 2
    # блок термостабилизации (СТР) — дальний правый угол крыши
    s += o.box(104, top, 22, 38, 24, 38, "url(#alu_l)", "url(#alu_t)", "url(#alu_f)", "#5f6b78", 0.6)
    s += f'<g transform="{o.front_canvas(104, top + 24, 22)}">' + text(19, 15, "СТР", 9, "bold", "#2b3541", "middle") + "</g>"
    for k in range(3):
        pp = [o.P(108 + k * 11, top + 24, 44), o.P(108 + k * 11, top + 36, 44), o.P(114 + k * 11, top + 36, 44), o.P(114 + k * 11, top + 24, 44)]
        s += line(rounded(pp, 3), "#7a3a18", 2.6) + line(rounded(pp, 3), "#d98a55", 1.6)
    # оптический терминал межспутниковой связи (ISL) — ближний край
    s += o.box(44, top, -66, 40, 12, 40, "url(#alu_l)", "url(#alu_t)", "url(#alu_f)", "#5f6b78", 0.6)
    s += o.cylinder((64, top + 12, -46), (0, 1, 0), 13, 16, "url(#alu_dk)", "url(#alu_t)")
    s += o.cylinder((64, top + 28, -46), (-0.72, 0.69, 0.0), 12, 30, "url(#alu_l)", "url(#lens)")
    # GPS/ГЛОНАСС
    s += o.cylinder((26, top, 40), (0, 1, 0), 20, 6, "url(#alu_dk)", "url(#alu_t)")
    s += o.cylinder((26, top + 6, 40), (0, 1, 0), 14, 10, "url(#dome)", "#ffffff")
    ANCHORS[10] = o.on_left(0, dy / 2, dz / 2, 10, 46)
    ANCHORS["gps"] = o.P(26, top + 3, 20)
    ANCHORS["isl"] = o.P(44, top + 6, -66)
    ANCHORS["plat_100"] = o.on_left(0, dy / 2, dz / 2, dz / 2, 150)
    ANCHORS["plat_data"] = o.on_left(0, dy / 2, dz / 2, dz / 2, 203)
    pg, pi, pt = o.P(26, top + 16, 40), o.P(42, top + 50, -46), o.P(123, top + 24, 22)
    labels = text(pg[0] - 8, pg[1] - 14, "GPS/ГЛОНАСС", 9, "semibold", "#3f4b5a", "middle")
    labels += text(pi[0] - 2, pi[1] - 16, "ISL", 9, "semibold", "#3f4b5a", "middle")
    labels += text(pt[0] + 14, pt[1] - 30, "термостаб.", 9, "semibold", "#3f4b5a", "middle")
    return f'<g filter="url(#shadow)">{s}</g>' + labels


# =================================================================================
# Соединения
# =================================================================================
LANE_TX, LANE_RX, LANE_CT, LANE_PW = 852, 870, 888, 908


def conn_antenna_to_ppm():
    """8 коаксиалов: подрешётка 2×2 -> передний ППМ."""
    s = ""
    ports = sorted(PORTS2, key=lambda t: t[0][0])          # слева направо
    targets = ppm_connectors()                              # сверху вниз
    n = len(ports)
    for rank, (p, col, dk) in enumerate(ports):
        inner = n - 1 - rank                                # правый порт — внутренняя дорожка
        y_l = 752 + rank * 5.0
        x_t = CARD2[0] + CARD2[2] + 12 + rank * 5.0
        tgt = targets[inner]
        wp = [p, (p[0], y_l), (x_t, y_l), (x_t, tgt[1]), (tgt[0] - 2, tgt[1])]
        pts_ = rounded(wp, 7)
        light = TX_L if col == TX else RX_L
        s += cable(pts_, col, dk, light, 1.7, arrows=(0.55,), reverse=(col == TX), arrow_size=6.5)
    return s


def conn_bundles():
    """Пучки к ППМ: TX, RX, M-LVDS/LOAD, 27 В — идут под элементами и
    поднимаются к переднему ППМ снизу (разъёмы на скрытой задней грани)."""
    s = ""
    bx0 = PPM.P(0, 0, BR["z0"])[0]                 # левый край передней грани ППМ
    y_up = AXIS_Y + 10                              # куда уходят кабели (за корпус)
    sp = 2.3
    # нижние дорожки поднимаются левее — так пучки не пересекаются
    x_pw, x_ct, x_load, x_rx, x_tx = bx0 + 5, bx0 + 16, bx0 + 25, bx0 + 29, bx0 + 41
    # TX: от выходного ряда платы TX влево к ППМ
    src = board_bottom_points(TXB, 5)
    for k, p in enumerate(src):
        y = LANE_TX + (k - 2) * sp
        xr = x_tx + (4 - k) * sp
        wp = [p, (p[0], y), (xr, y), (xr, y_up)]
        s += cable(rounded(wp, 12), TX, TX_D, TX_L, 1.4)
    # RX: от ППМ к плате RX
    src = board_bottom_points(RXB, 5)
    for k, p in enumerate(src):
        y = LANE_RX + (k - 2) * sp
        xr = x_rx + (4 - k) * sp
        wp = [(xr, y_up), (xr, y), (p[0], y), p]
        s += cable(rounded(wp, 12), RX, RX_D, RX_L, 1.4)
    # стрелки направления и стяжки на пучках
    for x in (760, 900):
        s += arrowhead((x, LANE_TX), math.pi, 12, TX, TX_D)
        s += arrowhead((x + 40, LANE_RX), 0, 12, RX, RX_D)
    for x in (712, 990):
        s += rect(x, LANE_TX - 9, 4, 30, "#9aa5b1", "#5f6b78", 0.5, 1.5)
    # M-LVDS шлейф + отдельная линия LOAD
    pc = CTL.on_left(0, CB_H / 2, CB_D / 2, 62, 172)
    wp = [pc, (pc[0], LANE_CT), (x_ct, LANE_CT), (x_ct, y_up)]
    s += ribbon(rounded(wp, 14), 7)
    pl = CTL.on_left(0, CB_H / 2, CB_D / 2, 128, 172)
    wp = [pl, (pl[0], LANE_CT + 9), (x_load, LANE_CT + 9), (x_load, y_up)]
    s += line(rounded(wp, 14), CT_D, 2.4) + line(rounded(wp, 14), CT, 1.5)
    s += arrowhead((840, LANE_CT), math.pi, 12, CT, CT_D)
    s += arrowhead((1100, LANE_CT + 9), math.pi, 9, CT, CT_D)
    s += text(pc[0] - 7, pc[1] + 42, "M-LVDS", 8.5, "bold", CT_D, "end")
    s += text((pc[0] + pl[0]) / 2 + 1, pl[1] + 56, "LOAD", 8.5, "bold", CT_D, "middle")
    # питание 27 В (две шины)
    for k, key in enumerate(("psu_out1", "psu_out2")):
        p = ANCHORS[key]
        y = LANE_PW + k * 5
        xd = p[0] - 22 - k * 6
        xr = x_pw + (1 - k) * 4.5
        wp = [p, (xd, p[1]), (xd, y), (xr, y), (xr, y_up)]
        s += cable(rounded(wp, 12), PW, PW_D, PW_L, 2.2)
    s += arrowhead((880, LANE_PW + 2.5), math.pi, 12, PW, PW_D)
    s += text(1460, LANE_PW + 24, "2 шины 27 В", 8.5, "bold", PW_D, "middle")
    # отводы 27 В к SDR и плате управления
    top_pt = SDR.P(SD_T / 2, -SD_H / 2, -SD_D / 2 + 26)
    x_tap = SDR.P(0, 0, 0)[0] - 10
    wp = [(x_tap, LANE_PW), (x_tap, top_pt[1] + 14), (top_pt[0], top_pt[1] + 14), top_pt]
    s += cable(rounded(wp, 8), PW, PW_D, PW_L, 1.8)
    top_pt = CTL.P(0, -CB_H / 2, -CB_D / 2 + 16)
    s += cable([(top_pt[0], LANE_PW), top_pt], PW, PW_D, PW_L, 1.8)
    return s


def conn_beams():
    """4 TX-луча SDR -> плата TX, 4 RX-луча плата RX -> SDR, данные SDR <-> управление."""
    s = ""
    tx_in = board_top_points(TXB)
    rx_out = board_top_points(RXB)
    sdr_tx = sdr_left_points("tx")
    sdr_rx = sdr_left_points("rx")
    lane_tx, lane_rx = 488, 504
    for k in range(4):
        y = lane_tx + k * 3.2
        xv = SDR.P(0, 0, SD_D / 2)[0] - 5 - k * 2.8
        wp = [sdr_tx[k], (xv, sdr_tx[k][1]), (xv, y), (tx_in[k][0], y), tx_in[k]]
        s += cable(rounded(wp, 10), TX, TX_D, TX_L, 1.6)
        p = sdr_tx[k]
        s += arrowhead((p[0] - 9, p[1]), math.pi, 7, TX, TX_D)
    for k in range(4):
        y = lane_rx + k * 3.2
        xv = SDR.P(0, 0, SD_D / 2)[0] - 16 - k * 2.8
        wp = [rx_out[k], (rx_out[k][0], y), (xv, y), (xv, sdr_rx[k][1]), sdr_rx[k]]
        s += cable(rounded(wp, 10), RX, RX_D, RX_L, 1.6)
        p = sdr_rx[k]
        s += arrowhead((p[0] - 5, p[1]), 0, 7, RX, RX_D)
    s += arrowhead((1150, lane_tx + 4.8), math.pi, 11, TX, TX_D)
    s += arrowhead((1250, lane_rx + 4.8), 0, 11, RX, RX_D)
    s += text(tx_in[1][0], lane_tx - 7, "4 луча TX", 9, "bold", TX)
    s += text(rx_out[3][0] + 22, lane_rx + 30, "4 луча RX", 9, "bold", RX)
    # данные SDR -> плата управления (M-LVDS/SPI/CAN): к переднему торцу платы
    edge_x = CTL.P(CB_T / 2, 0, -CB_D / 2)[0]
    for k in range(2):
        p = SDR.on_left(0, SD_H / 2, SD_D / 2, 8, 198 + k * 12)
        s += line([p, (edge_x, p[1])], CT_D, 2.4) + line([p, (edge_x, p[1])], CT, 1.5)
        s += arrowhead((edge_x + 9, p[1]), math.pi, 7, CT, CT_D)
    return s


def conn_platform():
    s = ""
    # 100 В: платформа -> ВИП
    a, b = ANCHORS["plat_100"], ANCHORS["psu_in"]
    wp = [a, (a[0] - 14, a[1]), (a[0] - 14, b[1] + 26), (b[0] + 30, b[1] + 26), (b[0] + 30, b[1]), b]
    s += cable(rounded(wp, 10), PW, PW_D, PW_L, 3.0, arrows=(0.45,), reverse=False, arrow_size=11)
    s += text(a[0] - 40, b[1] + 44, "100 В", 8.5, "bold", PW_D, "middle")
    # PPS/эфемериды и ISL -> SDR
    for k, key in enumerate(("gps", "isl")):
        p = ANCHORS[key]
        tgt = SDR.on_left(SD_GAP, SD_H / 2, SD_D / 2, 112 + k * 12, 0)
        y = 526 + k * 7
        wp = [p, (p[0], y), (tgt[0], y), tgt]
        s += line(rounded(wp, 10), CT_D, 2.4) + line(rounded(wp, 10), CT, 1.5)
        s += arrowhead((1610 + k * 40, y), math.pi, 9, CT, CT_D)
    s += text(1650, 519, "PPS · эфемериды · ISL", 8.5, "bold", CT_D, "middle")
    return s


def zoom_lines():
    s = ""
    x, y, w, h = CARD2
    for p, q in ((ANCHORS["sub_tl"], (x + 4, y + 4)), (ANCHORS["sub_br"], (x + 4, y + h - 4))):
        s += line([p, q], "#6f7f92", 0.9, 'stroke-dasharray="4 3"')
    p1, p2 = ANCHORS["ppm_front_tl"], ANCHORS["ppm_front_bl"]
    q1, q2 = ANCHORS["tray_tl"], ANCHORS["tray_bl"]
    s += line([p1, q1], "#6f7f92", 0.9, 'stroke-dasharray="4 3"')
    s += line([p2, q2], "#6f7f92", 0.9, 'stroke-dasharray="4 3"')
    return s


# =================================================================================
# Выноски, панель, легенда, лента
# =================================================================================
CALLOUTS = [
    # (номер, x, y, ширина текста, заголовок, пояснение)
    (1, 40, 128, 210, "Антенное полотно 1,0×1,2 м", "396 АЭ, стековые патчи, круговая поляризация"),
    (2, 262, 330, 190, "Подрешётка 2×2 → 1 ППМ", "Нижний Rx-слой и верхний Tx-слой, у каждого АЭ два порта"),
    (3, 500, 128, 214, "99 ППМ в отдельных корпусах", "8 ВЧ к антенне, 8 ВЧ к сети, 27 В, M-LVDS, CAN, LOAD"),
    (4, 680, 330, 214, "Внутри ППМ", "ФВ 7 бит, АТТ 6 бит, МШУ NF<0,6 дБ, GaN УМ 2,5–5 Вт, ППФ Rx 1980–2010 / Tx 2170–2200 МГц, PMIC 27→12/6/3,3/1,5 В"),
    (5, 940, 128, 200, "TX-распределение", "4 драйвера +25…+30 дБм → 4 делителя 1:99, потери ~24 дБ"),
    (6, 990, 330, 172, "RX-комбинирование", "4 сумматора 99:1 + буфер/МШУ, когерентное сложение +20 дБ"),
    (7, 1185, 128, 172, "Распределение M-LVDS", "4 хаба DS91M124, линия LOAD ко всем ППМ"),
    (8, 1372, 330, 200, "SDR TREVO №1 и №2", "ARM: веса, MAC, RRC; FPGA: 4 IQ-потока, компенсация Доплера; RFSoC: ЦАП/АЦП"),
    (9, 1522, 432, 150, "Центральный ВИП 100→27 В", "Резервированный, 2 шины 27 В"),
    (10, 1702, 300, 176, "М-платформа ИСС Решетнёва", "Бортовая сеть 100 В, GPS/ГЛОНАСС (PPS, эфемериды), ISL, термостабилизация"),
]


def callouts():
    s = ""
    for num, x, y, tw_, title, desc in CALLOUTS:
        tl = wrap(title, 13.5, tw_, "bold")
        dl = wrap(desc, 11.5, tw_, "regular")
        bx, by, bs = x, y, 24
        tx0 = x + bs + 9
        lines_h = len(tl) * 16 + len(dl) * 14.5
        ax, ay = ANCHORS[num]
        # линия-лидер: вниз от плашки, затем к элементу
        lx = bx + bs / 2
        ly0 = by + bs
        y_knee = max(ly0 + 4, min(ay - 26, by + bs + lines_h + 10))
        wp = [(lx, ly0), (lx, y_knee), (ax, ay)] if abs(ax - lx) > 2 else [(lx, ly0), (ax, ay)]
        s += line(wp, LEADER, 1.0)
        s += circle(ax, ay, 3.2, "#ffffff", NAVY, 1.4)
        s += circle(ax, ay, 1.2, NAVY)
        s += rect(bx, by, bs, bs, NAVY, rx=3)
        s += text(bx + bs / 2, by + 17, str(num), 13, "bold", "#ffffff", "middle")
        yy = by + 11
        for t in tl:
            s += text(tx0, yy + 5, t, 13.5, "bold", INK)
            yy += 16
        yy += 1
        for t in dl:
            s += text(tx0, yy + 4, t, 11.5, "regular", GREY_TXT)
            yy += 14.5
    return s


PARAMS = [
    ["4 луча", "396 АЭ", "99 ППМ", "1584 ВЧ-соединения"],
    ["Rx 1980–2010 МГц", "Tx 2170–2200 МГц", "полоса 10 МГц"],
    ["ЭИИМ 41 дБВт/луч", "G/T 5,6 дБ/К", "сканирование ±41° (аз.), 40° (у.м.)"],
    ["Потребление ~950–1000 Вт", "масса ~40–55 кг"],
]
LEGEND = [(TX, TX_D, "красный — TX"), (RX, RX_D, "синий — RX"), (PW, PW_D, "зелёный — питание"),
          (CT, CT_D, "жёлтый — управление и данные"), (GR, GR_D, "серый — конструктив")]


def panel():
    x, y, w = 1398, 22, 494
    size = 12.5
    rows_h = 22
    h = 34 + rows_h * len(PARAMS) + 6
    s = rect(x, y, w, h, "url(#panel)", "#bccbdb", 1, 10, 'filter="url(#cardshadow)"')
    s += text(x + 16, y + 21, "ОСНОВНЫЕ ПАРАМЕТРЫ", 10, "bold", "#6b7a8c", extra='letter-spacing="1"')
    yy = y + 44
    for row in PARAMS:
        cx = x + 16
        for i, item in enumerate(row):
            if i:
                s += line([(cx + 6, yy - 10), (cx + 6, yy + 2)], "#9fb1c4", 1.1)
                cx += 13
            s += text(cx, yy, item, size, "semibold", INK)
            cx += text_w(item, size, "semibold")
        yy += rows_h
    # легенда
    ly = y + h + 12
    lh = 58
    s += rect(x, ly, w, lh, "url(#panel)", "#bccbdb", 1, 10, 'filter="url(#cardshadow)"')
    items = [(LEGEND[0], x + 16, ly + 22), (LEGEND[1], x + 176, ly + 22), (LEGEND[2], x + 318, ly + 22),
             (LEGEND[3], x + 16, ly + 44), (LEGEND[4], x + 254, ly + 44)]
    for (col, dk, label), lx, lyy in items:
        s += line([(lx, lyy - 4), (lx + 26, lyy - 4)], dk, 4.6)
        s += line([(lx, lyy - 4), (lx + 26, lyy - 4)], col, 3.2)
        s += text(lx + 34, lyy, label, 12, "medium", INK)
    return s


CHEVRONS = ["Антенное полотно", "ППМ (×99)", "Распределение и комбинирование", "Цифровое ядро SDR", "Спутниковая платформа"]


def chevrons():
    s = ""
    x0, y0, hgt, gap, notch = 40, 962, 70, 6, 26
    total = W - 80
    widths = [300, 300, 460, 380, 0]
    widths[4] = total - sum(widths[:4]) - gap * 4
    x = x0
    for i, label in enumerate(CHEVRONS):
        w = widths[i]
        left_notch = notch if i else 0
        pts_ = [(x, y0), (x + w - notch, y0), (x + w, y0 + hgt / 2), (x + w - notch, y0 + hgt),
                (x, y0 + hgt), (x + left_notch, y0 + hgt / 2)]
        if i == 4:
            pts_ = [(x, y0), (x + w, y0), (x + w, y0 + hgt), (x, y0 + hgt), (x + left_notch, y0 + hgt / 2)]
        s += poly(pts_, f"url(#chev{i})", "none", 0, 'filter="url(#cardshadow)"')
        s += poly(pts_[:2] + [(pts_[1][0] + (notch * 0.5 if i < 4 else 0), y0 + 6), (x + left_notch * 0.25, y0 + 6)],
                  "#ffffff", extra='fill-opacity="0.12"')
        cx = x + (w + left_notch - (notch if i < 4 else 0)) / 2
        s += text(cx, y0 + hgt / 2 + 6, label, 17, "bold", "#ffffff", "middle")
        x += w + gap
    return s


def title():
    s = text(40, 66, "Бортовая 4-лучевая АФАР S-диапазона Direct-to-Cell: взрыв-схема", 33, "bold", NAVY)
    s += rect(40, 82, 96, 4, "#2a6cbb", rx=2)
    s += rect(140, 82, 28, 4, "#9cc7ff", rx=2)
    return s


def axis_line():
    return line([(30, AXIS_Y), (1900, AXIS_Y)], "#9aabbf", 0.9, 'stroke-dasharray="10 4 2 4" stroke-opacity="0.7"')


def build():
    body = []
    body.append(rect(0, 0, W, H, "url(#bg)"))
    body.append(rect(0, 0, W, H, "url(#bgspot)"))
    body.append(title())
    # тени на «полу»
    for (l, r), ox in zip(FOOT, OX):
        if r - l > 1:
            body.append(floor_shadow(ox + (l + r) / 2, (r - l) * 0.9))
    body.append(floor_shadow(OX[9] + 110, 260))
    body.append(axis_line())
    # слои: от дальнего (справа) к ближнему (слева)
    layers = {}
    layers[10] = layer_platform()
    layers[9] = layer_psu()
    layers[8] = layer_sdr()
    layers[7] = layer_ctl_board()
    layers[6] = layer_rx_board()
    layers[5] = layer_tx_board()
    layers[4] = layer_open_ppm()
    layers[3] = layer_ppm_row()
    layers[1] = layer_antenna()
    layers[2] = layer_inset_subarray()
    body.append(conn_bundles())
    for k in (10, 9, 8, 7, 6, 5):
        body.append(layers[k])
    body.append(conn_beams())
    body.append(conn_platform())
    body.append(layers[4])
    body.append(layers[3])
    body.append(zoom_lines())
    body.append(layers[1])
    body.append(layers[2])
    body.append(conn_antenna_to_ppm())
    body.append(callouts())
    body.append(panel())
    body.append(chevrons())
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
           f"<title>Бортовая 4-лучевая АФАР S-диапазона Direct-to-Cell: взрыв-схема</title>"
           + defs() + "".join(body) + "</svg>")
    OUT_SVG.write_text(svg, encoding="utf-8")
    print(f"written {OUT_SVG} ({len(svg) / 1024:.0f} KiB)")


if __name__ == "__main__":
    build()
