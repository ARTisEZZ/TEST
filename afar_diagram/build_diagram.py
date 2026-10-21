#!/usr/bin/env python3
"""Структурная схема бортовой 4-лучевой АФАР S-диапазона (Direct-to-Cell).

Генерирует векторный SVG формата A3 (альбомная ориентация, 1 ед. = 0.1 мм).
Растровый PNG и PDF получаются из SVG скриптом render.js (Playwright/Chromium).

    python3 build_diagram.py            # -> afar_s_band_d2c.svg
"""
import os
import sys

from PIL import ImageFont

W, H = 4200, 2970  # A3 landscape, 0.1 мм
FONT = "Liberation Sans, Arial, DejaVu Sans, sans-serif"
FONT_FILES = {
    False: "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    True: "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
}

# Цветовое кодирование потоков: (линия/контур, заливка, тёмный для текста)
PAL = {
    "tx": ("#D62839", "#FDE8EA", "#9B1726"),   # красный: передача
    "rx": ("#1D5FB4", "#E4EEFB", "#123F7A"),   # синий: приём
    "pw": ("#23964A", "#E3F5E8", "#176A33"),   # зелёный: питание
    "ct": ("#E2A300", "#FFF4C9", "#7A5800"),   # жёлтый: управление/данные
    "gr": ("#7B8491", "#EEF0F3", "#3E4652"),   # серый: конструктив
    "ink": ("#1B2230", "#FFFFFF", "#1B2230"),
}
INK = "#1B2230"
MUTED = "#5A6372"
BAND = "#F4F5F7"
BAND_LINE = "#D7DBE1"
TAG = "#2B3445"

out = []
warnings = []
_fonts = {}


def emit(s):
    out.append(s)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tw(s, size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(FONT_FILES[bold], size)
    return _fonts[key].getlength(s)


def col(kind, i=0):
    return PAL[kind][i]


# ---------------------------------------------------------------- primitives
def text(x, y, s, size=24, bold=False, color=INK, anchor="start", rotate=None,
         maxw=None):
    """s — строка или список сегментов [(текст, цвет, bold), ...] (tspan)."""
    plain = s if isinstance(s, str) else "".join(seg[0] for seg in s)
    if maxw is not None and tw(plain, size, bold) > maxw:
        warnings.append(f"text overflow ({tw(plain, size, bold):.0f}>{maxw}): {plain}")
    tr = f' transform="rotate({rotate} {x} {y})"' if rotate else ""
    if isinstance(s, str):
        body = esc(s)
    else:
        parts = []
        for seg in s:
            t, c = seg[0], seg[1]
            b = seg[2] if len(seg) > 2 else bold
            parts.append(f'<tspan fill="{c}" font-weight="{700 if b else 400}">{esc(t)}</tspan>')
        body = "".join(parts)
    emit(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
         f'font-weight="{700 if bold else 400}" fill="{color}" '
         f'text-anchor="{anchor}"{tr}>{body}</text>')


def rect(x, y, w, h, fill="none", stroke=None, sw=2, rx=8, dash=None, opacity=None):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    da = f' stroke-dasharray="{dash}"' if dash else ""
    op = f' fill-opacity="{opacity}"' if opacity is not None else ""
    emit(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
         f'fill="{fill}"{op}{st}{da}/>')


def line(x1, y1, x2, y2, color, sw=2, dash=None, cap="butt"):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    emit(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
         f'stroke="{color}" stroke-width="{sw}" stroke-linecap="{cap}"{da}/>')


def dot(x, y, kind, r=7):
    emit(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{col(kind)}" '
         f'stroke="#FFFFFF" stroke-width="2"/>')


ARROW_S = {"n": 1.7, "big": 2.6, "s": 1.15}  # масштаб наконечника
ARROW_BACK = {k: 9.0 * s for k, s in ARROW_S.items()}  # длина от «выемки» до острия


def markers():
    emit("<defs>")
    for kind in PAL:
        c = col(kind)
        for sz, s in ARROW_S.items():
            emit(f'<marker id="ah-{kind}-{sz}" viewBox="0 0 12 10" refX="3" refY="5" '
                 f'markerUnits="userSpaceOnUse" markerWidth="{12 * s:.1f}" '
                 f'markerHeight="{10 * s:.1f}" orient="auto-start-reverse">'
                 f'<path d="M0,0 L12,5 L0,10 L3,5 Z" fill="{c}"/></marker>')
    emit("</defs>")


def _shift(p, q, dist):
    """Сдвигает точку p в сторону q на dist."""
    (x1, y1), (x2, y2) = p, q
    L = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 or 1.0
    return (x1 + (x2 - x1) / L * dist, y1 + (y2 - y1) / L * dist)


def wire(pts, kind, sw=4, end=True, start=False, dash=None, halo=BAND, size="n"):
    """Ортогональная линия потока со стрелкой и «ореолом» для чистых пересечений."""
    pts = [tuple(p) for p in pts]
    back = ARROW_BACK[size]
    if end:
        pts[-1] = _shift(pts[-1], pts[-2], back)
    if start:
        pts[0] = _shift(pts[0], pts[1], back)
    d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    if halo:
        emit(f'<path d="{d}" fill="none" stroke="{halo}" stroke-width="{sw + 9}" '
             f'stroke-linejoin="miter"/>')
    mk = ""
    if end:
        mk += f' marker-end="url(#ah-{kind}-{size})"'
    if start:
        mk += f' marker-start="url(#ah-{kind}-{size})"'
    da = f' stroke-dasharray="{dash}"' if dash else ""
    emit(f'<path d="{d}" fill="none" stroke="{col(kind)}" stroke-width="{sw}" '
         f'stroke-linejoin="miter"{da}{mk}/>')


def offset_polyline(pts, d):
    """Смещение ортогональной ломаной на d (левая нормаль, «ленточная» трассировка)."""
    res = []
    n = len(pts)
    for i in range(n):
        nx = ny = 0.0
        for a, b in ((i - 1, i), (i, i + 1)):
            if 0 <= a and b < n:
                dx = pts[b][0] - pts[a][0]
                dy = pts[b][1] - pts[a][1]
                L = (dx * dx + dy * dy) ** 0.5
                nx += -dy / L
                ny += dx / L
        # для угла 90° сумма нормалей даёт нужный угловой сдвиг, для конца — одна нормаль
        res.append((pts[i][0] + nx * d, pts[i][1] + ny * d))
    return res


def ribbon(center, kind, n=4, spacing=18, sw=3.5, halo=BAND, **kw):
    for i in range(n):
        d = (i - (n - 1) / 2) * spacing
        wire(offset_polyline(center, d), kind, sw=sw, halo=halo, **kw)


def slash(x, y, kind, label, vertical=True, side=1):
    c = col(kind)
    line(x - 15, y + 15, x + 15, y - 15, c, 3.5) if vertical else line(x - 15, y + 15, x + 15, y - 15, c, 3.5)
    text(x + side * 24, y + 9, label, 24, True, col(kind, 2), "start" if side > 0 else "end")


def block(x, y, w, h, kind, title=None, lines=(), tsize=28, lsize=24, stack=0,
          align="middle", pad=18, fill=None, sw=3, title_color=None, rx=10, lh=1.25):
    stroke, tint, dark = PAL[kind]
    fill = fill or tint
    for k in range(stack, 0, -1):
        rect(x + 7 * k, y + 7 * k, w, h, fill, stroke, 2, rx)
    rect(x, y, w, h, fill, stroke, sw, rx)
    items = []
    if title:
        for t in ([title] if isinstance(title, str) else title):
            items.append((t, tsize, True, title_color or dark))
    for l in lines:
        if isinstance(l, tuple) and len(l) == 4 and isinstance(l[1], int):
            items.append(l)
        else:
            items.append((l, lsize, False, INK))
    total = sum(s * lh for _, s, _, _ in items) - (items[-1][1] * (lh - 1) if items else 0)
    cy = y + (h - total) / 2
    for t, s, b, c in items:
        if align == "middle":
            tx_, anc = x + w / 2, "middle"
        else:
            tx_, anc = x + pad, "start"
        text(tx_, cy + s * 0.82, t, s, b, c, anc, maxw=(w - 2 * pad + 6) if align == "middle" else (w - pad - 12))
        cy += s * lh


def ptag(x, y, direction, label="27 В"):
    """Сетевая метка питания: зелёный флажок, указывающий в блок (direction: left/right/up/down)."""
    c, tint, dark = PAL["pw"]
    w_ = tw(label, 22, True) + 26
    h_ = 34
    if direction == "left":      # блок слева от метки
        x0, y0 = x + 12, y - h_ / 2
        pts = [(x, y), (x0, y0), (x0 + w_, y0), (x0 + w_, y0 + h_), (x0, y0 + h_)]
        tx_ = x0 + w_ / 2
    elif direction == "right":   # блок справа от метки
        x0, y0 = x - 12 - w_, y - h_ / 2
        pts = [(x, y), (x0 + w_, y0 + h_), (x0, y0 + h_), (x0, y0), (x0 + w_, y0)]
        tx_ = x0 + w_ / 2
    elif direction == "up":      # блок над меткой
        x0, y0 = x - w_ / 2, y + 12
        pts = [(x, y), (x0 + w_, y0), (x0 + w_, y0 + h_), (x0, y0 + h_), (x0, y0)]
        tx_ = x
    else:                        # блок под меткой
        x0, y0 = x - w_ / 2, y - 12 - h_
        pts = [(x, y), (x0, y0 + h_), (x0, y0), (x0 + w_, y0), (x0 + w_, y0 + h_)]
        tx_ = x
    emit('<polygon points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) +
         f'" fill="{tint}" stroke="{c}" stroke-width="2.5"/>')
    text(tx_, y0 + h_ / 2 + 8, label, 22, True, dark, "middle")


def amp(cx, y_top, kind, down=True, w=62, h=54):
    c, tint, _ = PAL[kind]
    if down:
        pts = [(cx - w / 2, y_top), (cx + w / 2, y_top), (cx, y_top + h)]
    else:
        pts = [(cx - w / 2, y_top + h), (cx + w / 2, y_top + h), (cx, y_top)]
    emit('<polygon points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) +
         f'" fill="{c}" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>')


def bpf(cx, cy, w=60, h=46):
    c, tint, dark = PAL["gr"]
    rect(cx - w / 2, cy - h / 2, w, h, "#FFFFFF", dark, 2.5, 4)
    for k, dy in enumerate((-13, 0, 13)):
        y0 = cy + dy
        x0 = cx - 16
        emit(f'<path d="M {x0},{y0} q 8,-8 16,0 t 16,0" fill="none" stroke="{dark}" '
             f'stroke-width="2.2"/>')
        if k != 1:
            line(cx + 6, y0 - 6, cx - 6, y0 + 6, dark, 2)


def tree_icon(cx, top, width, height, levels, kind, invert=False):
    """Иконка дерева деления (Вилкинсон): корень сверху (или снизу при invert)."""
    c = col(kind)
    step = height / levels
    nodes = [cx]
    segs = []
    for L in range(levels):
        y0 = L * step
        new = []
        for x in nodes:
            dx = width / (2 ** (L + 2))
            ym = y0 + step * 0.45
            segs.append((x, y0, x, ym))
            segs.append((x - dx, ym, x + dx, ym))
            for s in (-1, 1):
                segs.append((x + s * dx, ym, x + s * dx, y0 + step))
                new.append(x + s * dx)
        nodes = new
    for x1, y1, x2, y2 in segs:
        if invert:
            y1, y2 = height - y1, height - y2
        line(x1, top + y1, x2, top + y2, c, 2.2)


# ------------------------------------------------------------------ layout
def build():
    emit(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="{FONT}">')
    markers()
    rect(0, 0, W, H, "#FFFFFF", None, 0, 0)

    # ---------------- header
    text(60, 92, "Бортовая 4-лучевая АФАР S-диапазона для спутниковой связи Direct-to-Cell",
         58, True, INK)
    text(60, 142, "Структурная схема: спутниковая платформа → цифровое ядро SDR → "
         "СВЧ-распределение → 99 ППМ → антенное полотно 396 АЭ", 30, False, MUTED)

    # ---------------- level bands
    bands = [
        (170, 450, "1 · ПЛАТФОРМА"),
        (470, 905, "2 · ЦИФРОВОЕ ЯДРО"),
        (925, 1440, "3 · СВЧ-РАСПРЕДЕЛЕНИЕ"),
        (1460, 2250, "4 · 99 ППМ"),
        (2270, 2935, "5 · АНТЕННОЕ ПОЛОТНО"),
    ]
    for y0, y1, label in bands:
        rect(60, y0, 3270, y1 - y0, BAND, BAND_LINE, 2, 10)
        rect(60, y0, 64, y1 - y0, TAG, None, 0, 10)
        rect(100, y0, 24, y1 - y0, TAG, None, 0, 0)
        text(100, (y0 + y1) / 2, label, 28, True, "#FFFFFF", "middle", rotate=-90,
             maxw=y1 - y0 - 30)
    for (y0, y1, _), (n0, _, _) in zip(bands, bands[1:]):
        ym = (y1 + n0) / 2
        emit(f'<polygon points="80,{ym - 7} 104,{ym - 7} 92,{ym + 9}" fill="{TAG}"/>')

    # ======================================================== LEVEL 1
    text(150, 212, "Спутниковая платформа: М-платформа ИСС Решетнёва — служебные системы КА",
         28, True, col("gr", 2))
    block(200, 240, 290, 150, "pw", "Бортовая сеть", [("100 В", 40, True, col("pw", 2)),
                                                       ("первичная шина КА", 22, False, MUTED)],
          tsize=28)
    block(580, 240, 500, 150, "pw", ["Центральный ВИП", "100 → 27 В"],
          ["резервированный (2 канала, шины А/Б)"], tsize=30, lsize=22)
    wire([(490, 315), (580, 315)], "pw", sw=5)

    block(1290, 240, 420, 150, "ct", "GPS / ГЛОНАСС",
          ["навигационный приёмник", ("PPS + эфемериды", 24, True, col("ct", 2))], tsize=30)
    block(1830, 240, 520, 150, "ct", ["Оптическая межспутниковая", "связь (ISL)"],
          ["трафик абонентов, служебные данные"], tsize=28, lsize=22)
    block(2560, 240, 480, 150, "gr", "Термостабилизация",
          ["тепловые трубы, радиаторы,", "обогреватели, термодатчики"], tsize=30, lsize=22)

    # 27 В: ВИП → левая вертикальная двойная шина
    for d in (-6, 6):
        wire([(640 + d, 390), (640 + d, 462 + d), (164 + d, 462 + d), (164 + d, 1515)],
             "pw", sw=4, end=False)
    text(660, 436, "27 В (2 шины А/Б)", 26, True, col("pw", 2))

    # PPS + эфемериды и трафик ISL → обе SDR (шина данных платформы)
    wire([(1500, 390), (1500, 462)], "ct", sw=4, end=False)
    wire([(2090, 390), (2090, 462)], "ct", sw=4, end=False, start=True)
    wire([(1330, 462), (2130, 462)], "ct", sw=4, end=False)
    wire([(1330, 462), (1330, 520)], "ct", sw=4)
    wire([(2130, 462), (2130, 520)], "ct", sw=4)
    dot(1500, 462, "ct")
    dot(2090, 462, "ct")
    text(1515, 428, "PPS, эфемериды", 22, True, col("ct", 2))
    text(2105, 428, "трафик ISL", 22, True, col("ct", 2))

    # ======================================================== LEVEL 2: SDR
    def sdr(x0, num, tag, mirror):
        rect(x0, 520, 930, 280, "#FFFFFF", INK, 3, 12)
        text(x0 + 22, 562, f"SDR TREVO №{num}", 32, True, INK)
        text(x0 + 908, 560, tag, 24, False, MUTED, "end")
        subs = [
            ("ARM", ["расчёт весов,", "MAC, RRC"]),
            ("FPGA", ["4 IQ-потока,", "компенсация", "Доплера"]),
            ("RFSoC", [[("ЦАП", col("tx", 2), True), (" / ", INK, False),
                        ("АЦП", col("rx", 2), True)]]),
        ]
        xs = [(25, 290), (330, 620), (660, 905)]
        if mirror:
            xs = [(930 - b, 930 - a) for a, b in xs]
        for (name, ls), (a, b) in zip(subs, xs):
            x, w = x0 + a, b - a
            rect(x, 585, w, 195, col("ct", 1), col("ct"), 2.5, 8)
            items = [(name, 30, True)] + [(l, 24, False) for l in ls]
            total = 30 * 1.3 + 24 * 1.25 * len(ls) - 24 * 0.25
            cy = 585 + (195 - total) / 2
            for t, s, b_ in items:
                text(x + w / 2, cy + s * 0.82, t, s, b_, col("ct", 2) if b_ else INK, "middle",
                     maxw=w - 20)
                cy += s * (1.3 if b_ else 1.25)
        # внутренние обмены ARM ⇄ FPGA ⇄ RFSoC
        for (a, b), (c_, d_) in zip(xs, xs[1:]):
            l_, r_ = (x0 + b, x0 + c_) if not mirror else (x0 + d_, x0 + a)
            wire([(l_, 682), (r_, 682)], "ct", sw=3, start=True, halo=None, size="s")

    sdr(470, 1, "основной", False)
    sdr(2060, 2, "резерв (1+1)", True)
    rect(1600, 595, 260, 190, col("gr", 1), col("gr", 2), 3, 10)
    text(1730, 640, "Коммутатор", 26, True, col("gr", 2), "middle")
    text(1730, 670, "резерва 1+1", 26, True, col("gr", 2), "middle")
    text(1730, 715, [("4 × TX ", col("tx", 2), True), ("2→1", INK, False)], 22, False, INK,
         "middle")
    text(1730, 748, [("4 × RX ", col("rx", 2), True), ("1→2", INK, False)], 22, False, INK,
         "middle")

    # SDR ⇄ коммутатор: по 4 TX (≈0 дБм) и 4 RX
    for i in range(4):
        yt = 612 + 18 * i
        yr = 712 + 18 * i
        wire([(1375, yt), (1600, yt)], "tx", sw=3.5, halo=None)
        wire([(1600, yr), (1375, yr)], "rx", sw=3.5, halo=None)
        wire([(2085, yt), (1860, yt)], "tx", sw=3.5, halo=None)
        wire([(1860, yr), (2085, yr)], "rx", sw=3.5, halo=None)
    for cx in (1488, 1972):
        text(cx, 600, "4 × TX ≈0 дБм", 22, True, col("tx", 2), "middle")
        text(cx, 806, "4 × RX", 22, True, col("rx", 2), "middle")

    # Питание SDR №1 от шины, SDR №2 — сетевая метка
    wire([(170, 660), (470, 660)], "pw", sw=4)
    text(190, 648, "27 В", 22, True, col("pw", 2))
    ptag(2990, 660, "left")

    # ======================================================== LEVEL 3
    # TX: коммутатор → 4 драйвера → 4 делителя 1:99
    ribbon([(1667, 785), (1667, 980), (395, 980), (395, 1060)], "tx")
    text(610, 1043, "4 × TX (лучи 1–4), ≈0 дБм", 24, True, col("tx", 2))
    block(230, 1060, 330, 140, "tx", "4 × Драйвер", [("+25…+30 дБм", 26, True, INK)],
          tsize=30, stack=3)
    wire([(170, 1130), (230, 1130)], "pw", sw=4)
    for i in range(4):
        y = 1103 + 18 * i
        wire([(560, y), (640, y)], "tx", sw=3.5, halo=None)
    block(640, 1060, 560, 180, "tx", "4 × Делитель 1:99",
          ["дерево Вилкинсона,", "9 каскадов", ("потери ≈24 дБ", 24, True, col("tx", 2))],
          tsize=30, stack=3, align="left", pad=24)
    tree_icon(1110, 1088, 130, 120, 3, "tx")
    wire([(920, 1240), (920, 1460)], "tx", sw=9, size="big")
    slash(920, 1300, "tx", "396")
    text(945, 1398, "396 линий к ППМ (4 × 99)", 24, True, col("tx", 2))
    text(945, 1428, "≈+1…+6 дБм на вход ППМ", 22, False, col("tx", 2))

    # RX: 396 от ППМ → 4 сумматора 99:1 → 4 буфера/МШУ → коммутатор
    wire([(2580, 1460), (2580, 1240)], "rx", sw=9, size="big")
    slash(2580, 1300, "rx", "396", side=-1)
    text(2560, 1428, "396 линий от ППМ", 24, True, col("rx", 2), "end")
    block(2300, 1060, 560, 180, "rx", "4 × Сумматор 99:1",
          ["когерентное сложение", ("+20 дБ (10·lg 99)", 24, True, col("rx", 2))],
          tsize=30, stack=3, align="left", pad=170)
    tree_icon(2385, 1088, 130, 120, 3, "rx", invert=True)
    for i in range(4):
        y = 1103 + 18 * i
        wire([(2860, y), (2930, y)], "rx", sw=3.5, halo=None)
    block(2930, 1060, 310, 140, "rx", "4 × Буфер / МШУ", ["перед АЦП RFSoC"], tsize=28,
          lsize=22, stack=3)
    ptag(3085, 1221, "up")
    ribbon([(3085, 1060), (3085, 980), (1793, 980), (1793, 785)], "rx")
    text(2320, 1043, "4 × RX (лучи 1–4)", 24, True, col("rx", 2))

    # Управление: SDR → блок распределения M-LVDS
    wire([(1330, 800), (1330, 1030), (1470, 1030), (1470, 1070)], "ct", sw=4.5)
    wire([(2130, 800), (2130, 1030), (1990, 1030), (1990, 1070)], "ct", sw=4.5)
    for x, anc in ((1314, "end"), (2146, "start")):
        text(x, 834, "LVDS/M-LVDS пакеты коэффициентов", 23, True, col("ct", 2), anc)
        text(x, 864, "CAN телеметрия", 23, True, col("ct", 2), anc)
        text(x, 894, "PPS/LOAD", 23, True, col("ct", 2), anc)
    rect(1400, 1070, 700, 230, col("ct", 1), col("ct"), 3, 10)
    text(1750, 1110, "Блок распределения M-LVDS", 28, True, col("ct", 2), "middle")
    text(1750, 1142, "4 хаба DS91M124", 24, False, INK, "middle")
    for k in range(4):
        hx = 1420 + 140 * k
        rect(hx, 1165, 125, 64, "#FFFFFF", col("ct"), 2.5, 6)
        text(hx + 62.5, 1206, f"Хаб {k + 1}", 22, True, col("ct", 2), "middle")
        line(hx + 62.5, 1229, hx + 62.5, 1300, col("ct"), 3.5)
        wire([(hx + 62.5, 1300), (hx + 62.5, 1460)], "ct", sw=3.5)
    for x_ in (2015, 2068):
        line(x_, 1255, x_, 1300, col("ct"), 3.5)
        wire([(x_, 1300), (x_, 1460)], "ct", sw=3.5)
    text(2015, 1248, "LOAD", 19, True, col("ct", 2), "middle")
    text(2068, 1248, "CAN", 19, True, col("ct", 2), "middle")
    text(1470, 1352, "4 × M-LVDS (≈25 ППМ на хаб)", 23, True, col("ct", 2), "end")
    text(2088, 1352, "LOAD → ко всем ППМ", 23, True, col("ct", 2))
    text(2088, 1384, "CAN телеметрия", 23, True, col("ct", 2))
    ptag(1400, 1262, "right")

    # Примечания уровня 3
    rect(200, 1290, 680, 120, "#FFFFFF", col("gr"), 2, 8)
    text(222, 1330, [("Потери TX ~24 дБ", col("tx", 2), True),
                     (", компенсируются драйвером;", INK, False)], 25, False, INK, maxw=640)
    text(222, 1366, [("RX — когерентное сложение +20 дБ", col("rx", 2), True)], 25, False,
         INK, maxw=640)
    text(222, 1397, "(сигнал ×99 когерентно, шум — некогерентно)", 21, False, MUTED)

    rect(2640, 1290, 600, 120, "#FFFFFF", col("gr"), 2, 8)
    text(2660, 1328, "Резерв 1+1: при отказе SDR №1", 23, False, INK, maxw=560)
    text(2660, 1360, "коммутатор переводит 4 TX и 4 RX", 23, False, INK, maxw=560)
    text(2660, 1392, "на SDR №2 (идентичная конфигурация)", 23, False, INK, maxw=560)

    # ======================================================== LEVEL 4: 99 ППМ
    rect(200, 1460, 3040, 105, col("gr", 1), col("gr", 2), 2.5, 10)
    text(220, 1503, "99 × ППМ", 32, True, INK)
    text(220, 1536, "отдельные металлические корпуса", 21, False, MUTED)
    wire([(170, 1512), (200, 1512)], "pw", sw=4)
    labels = [f"ППМ {k}" for k in range(1, 9)] + [None] + [f"ППМ {k}" for k in range(91, 100)]
    x = 580
    for lab in labels:
        if lab is None:
            text(x + 140, 1522, "… 99 шт. …", 28, True, MUTED, "middle")
            x += 280
            continue
        hl = lab == "ППМ 1"
        rect(x, 1478, 122, 68, "#FFFFFF", INK if hl else col("gr", 2), 4 if hl else 2, 6)
        text(x + 61, 1520, lab, 21, True, INK if hl else col("gr", 2), "middle")
        x += 135
    # Теплоотвод
    wire([(3240, 1512), (3292, 1512), (3292, 315), (3040, 315)], "gr", sw=3.5, dash="14 9")
    text(3278, 700, "теплоотвод ППМ и SDR (тепловые трубы)", 22, True, col("gr", 2),
         "middle", rotate=-90)

    # ---- врезка ППМ
    IX0, IX1, IY0, IY1 = 200, 3240, 1620, 2235
    line(641, 1546, 641, 1620, INK, 3, dash="8 6")
    rect(IX0, IY0, IX1 - IX0, IY1 - IY0, "#FFFFFF", INK, 4, 14)
    emit(f'<path d="M {IX0},{IY0 + 46} L {IX0},{IY0 + 14} Q {IX0},{IY0} {IX0 + 14},{IY0} '
         f'L 660,{IY0} L 660,{IY0 + 46} Z" fill="{INK}"/>')
    text(222, IY0 + 32, "ППМ 1 — врезка (1 из 99)", 26, True, "#FFFFFF")

    TXC = [750, 890, 1030, 1170]
    RXC = [2270, 2410, 2550, 2690]
    H0 = "#FFFFFF"

    def connector(x, y, kind):
        rect(x - 12, y - 8, 24, 16, col("gr", 1), col("gr", 2), 2.5, 2)

    # Заголовки трактов
    text(240, 1745, "Передача (Tx)", 30, True, col("tx", 2))
    text(240, 1776, "4 канала → 4 АЭ", 22, False, MUTED)
    text(3215, 1745, "Приём (Rx)", 30, True, col("rx", 2), "end")
    text(3215, 1776, "4 АЭ → 4 канала", 22, False, MUTED, "end")

    # TX-тракт
    block(680, 1690, 560, 110, "tx", "Tx Core-Chip 4-канальный",
          ["ФВ 7 бит · АТТ 6 бит · сумматор 4:1"], tsize=26, lsize=23)
    rect(680, 1840, 560, 130, col("tx", 1), col("tx"), 2, 8, dash="8 5")
    rect(680, 2010, 560, 92, col("gr", 1), col("gr"), 2, 8, dash="8 5")
    text(240, 1885, "4 × GaN УМ", 28, True, col("tx", 2))
    text(240, 1917, "P1dB 2.5–5 Вт,", 23, False, INK)
    text(240, 1947, "back-off, DPD", 23, False, INK)
    text(240, 2050, "4 × ППФ Tx", 28, True, col("gr", 2))
    text(240, 2082, "2170–2200 МГц", 23, False, INK)
    for k, cx in enumerate(TXC):
        wire([(cx, 1600), (cx, 1690)], "tx", sw=3.5, halo=None)
        connector(cx, IY0, "tx")
        wire([(cx, 1800), (cx, 1878)], "tx", sw=3.5, halo=None)
        amp(cx, 1878, "tx", down=True)
        wire([(cx, 1932), (cx, 2033)], "tx", sw=3.5, halo=None)
        bpf(cx, 2056)
        wire([(cx, 2079), (cx, IY1)], "tx", sw=3.5, halo=H0)
        connector(cx, IY1, "tx")
        text(cx + 10, 2222, f"→АЭ{k + 1}", 20, True, col("tx", 2))

    # RX-тракт
    block(2200, 1690, 560, 110, "rx", "Rx Core-Chip 4-канальный",
          ["ФВ 7 бит · АТТ 6 бит · делитель 1:4"], tsize=26, lsize=23)
    rect(2200, 1840, 560, 130, col("rx", 1), col("rx"), 2, 8, dash="8 5")
    rect(2200, 2010, 560, 92, col("gr", 1), col("gr"), 2, 8, dash="8 5")
    text(3215, 1885, "4 × GaAs МШУ", 28, True, col("rx", 2), "end")
    text(3215, 1917, "NF < 0.6 дБ", 23, False, INK, "end")
    text(3215, 2050, "4 × ППФ Rx", 28, True, col("gr", 2), "end")
    text(3215, 2082, "1980–2010 МГц", 23, False, INK, "end")
    for k, cx in enumerate(RXC):
        wire([(cx, IY1), (cx, 2079)], "rx", sw=3.5, halo=H0)
        connector(cx, IY1, "rx")
        bpf(cx, 2056)
        wire([(cx, 2033), (cx, 1932)], "rx", sw=3.5, halo=None)
        amp(cx, 1878, "rx", down=False)
        wire([(cx, 1878), (cx, 1800)], "rx", sw=3.5, halo=None)
        wire([(cx, 1690), (cx, 1600)], "rx", sw=3.5, halo=None)
        connector(cx, IY0, "rx")
        text(cx + 10, 2222, f"←АЭ{4 - k}", 20, True, col("rx", 2))

    # Подписи разъёмов над врезкой
    text(960, 1591, "Tx 1–4 от делителей", 22, True, col("tx", 2), "middle")
    text(2480, 1591, "Rx 1–4 к сумматорам", 22, True, col("rx", 2), "middle")

    # ПЛИС / CPLD
    rect(1460, 1690, 590, 212, col("ct", 1), col("ct"), 3, 10)
    text(1755, 1728, "ПЛИС / CPLD", 28, True, col("ct", 2), "middle")
    for i, s in enumerate(["• декодирование M-LVDS", "• буфер состояний луча",
                           "• калибровка", "• SPI Master", "• LOAD"]):
        text(1490 + (280 if i >= 3 else 0), 1768 + 32 * (i if i < 3 else i - 3), s, 23,
             False, INK)
    # входы управления
    for x_, lab in ((1590, "M-LVDS"), (1755, "CAN"), (1920, "LOAD")):
        wire([(x_, 1600), (x_, 1690)], "ct", sw=3.5, halo=None)
        connector(x_, IY0, "ct")
        text(x_, 1591, lab, 22, True, col("ct", 2), "middle")
    # 27 В
    wire([(1425, 1600), (1425, 1940)], "pw", sw=4, halo=None)
    connector(1425, IY0, "pw")
    text(1425, 1591, "27 В", 22, True, col("pw", 2), "middle")
    # SPI + LOAD к Core-Chip
    wire([(1460, 1745), (1240, 1745)], "ct", sw=3.5, halo=H0)
    wire([(2050, 1745), (2200, 1745)], "ct", sw=3.5, halo=H0)
    text(1330, 1733, "SPI, LOAD", 20, True, col("ct", 2), "middle")
    text(2125, 1733, "SPI, LOAD", 20, True, col("ct", 2), "middle")

    # ВИП (PMIC)
    rect(1390, 1940, 660, 240, col("pw", 1), col("pw"), 3, 10)
    text(1720, 1980, "ВИП (PMIC)", 28, True, col("pw", 2), "middle")
    text(1720, 2018, "27 В → 12 / 6 / 3.3 / 1.5 В", 24, True, INK, "middle")
    text(1720, 2052, "+ sequencing для GaN", 24, False, INK, "middle")
    text(1720, 2090, "питание: УМ, МШУ, Core-Chip, ПЛИС", 21, False, MUTED, "middle")
    text(1720, 2122, "защита по току, телеметрия по CAN", 21, False, MUTED, "middle")
    wire([(1390, 1955), (1240, 1955)], "pw", sw=4, halo=None)
    wire([(2050, 1955), (2200, 1955)], "pw", sw=4, halo=None)
    wire([(1720, 1940), (1720, 1902)], "pw", sw=4, halo=None)
    text(1315, 1985, "Vg → Vd", 20, True, col("pw", 2), "middle")
    text(1315, 2007, "sequencing", 18, False, col("pw", 2), "middle")

    # Сводка разъёмов (врезка, справа внизу) и под врезкой слева
    rect(2800, 2106, 425, 118, "#FFFFFF", col("gr"), 2, 6)
    text(2815, 2132, "Разъёмы ППМ:", 21, True, col("gr", 2))
    text(2815, 2158, "8 × ВЧ к сети (4 Tx + 4 Rx)", 21, False, INK)
    text(2815, 2183, "8 × ВЧ к антенне (4 Rx + 4 Tx)", 21, False, INK)
    text(2815, 2208, "27 В · M-LVDS · CAN · LOAD", 21, False, INK)

    # ======================================================== LEVEL 5
    # Полотно 22 × 18
    GX, GY, CELL = 232, 2420, 26
    text(GX, 2402, "Антенное полотно 1.2 × 1.0 м: 22 × 18 = 396 АЭ", 26, True, INK)
    rect(GX - 6, GY - 6, 22 * CELL + 12, 18 * CELL + 12, "#FFFFFF", col("gr", 2), 2.5, 4)
    HC, HR = 14, 8
    for r in range(18):
        for c in range(22):
            x_ = GX + c * CELL + 3
            y_ = GY + r * CELL + 3
            if HC <= c <= HC + 1 and HR <= r <= HR + 1:
                rect(x_, y_, 20, 20, col("rx", 1), col("rx"), 1.6, 2)
                rect(x_ + 5, y_ + 5, 10, 10, col("tx"), None, 0, 1)
            else:
                rect(x_, y_, 20, 20, "#E7EAEE", "#A3AAB5", 1.2, 2)
    hx0, hy0 = GX + HC * CELL, GY + HR * CELL
    rect(hx0 - 2, hy0 - 2, 2 * CELL + 4, 2 * CELL + 4, "none", INK, 3.5, 3)
    # размеры
    line(GX, 2906, GX + 22 * CELL, 2906, MUTED, 1.8)
    for x_ in (GX, GX + 22 * CELL):
        line(x_, 2896, x_, 2916, MUTED, 1.8)
    text(GX + 11 * CELL, 2930, "1.2 м (22 АЭ, шаг ≈55 мм)", 22, False, MUTED, "middle")
    line(205, GY, 205, GY + 18 * CELL, MUTED, 1.8)
    for y_ in (GY, GY + 18 * CELL):
        line(195, y_, 215, y_, MUTED, 1.8)
    text(196, GY + 9 * CELL, "1.0 м (18 АЭ)", 22, False, MUTED, "middle", rotate=-90)

    # зум на подрешётку
    SX0, SX1, SY0, SY1 = 1470, 1940, 2400, 2850
    emit(f'<polygon points="{hx0 + 2 * CELL + 2},{hy0 - 2} {SX0},{SY0} {SX0},{SY1} '
         f'{hx0 + 2 * CELL + 2},{hy0 + 2 * CELL + 2}" fill="{col("gr", 1)}" fill-opacity="0.6" '
         f'stroke="{col("gr")}" stroke-width="1.8" stroke-dasharray="8 6"/>')
    rect(SX0, SY0, SX1 - SX0, SY1 - SY0, "#FFFFFF", col("gr"), 2, 8, dash="8 6")
    text(1080, 2636, "подрешётка 2×2", 26, True, INK, "middle")
    text(1080, 2668, "4 АЭ ↔ 1 ППМ", 26, True, INK, "middle")

    # элементы 2×2 (вид сверху): стековый патч с двумя портами
    elems = {  # имя: (x, y) верхнего левого угла
        "АЭ2": (1480, 2410), "АЭ4": (1760, 2410),
        "АЭ1": (1480, 2670), "АЭ3": (1760, 2670),
    }

    def trunc_sq(cx, cy, half, cut, fill, stroke):
        pts = [(cx - half + cut, cy - half), (cx + half, cy - half), (cx + half, cy + half - cut),
               (cx + half - cut, cy + half), (cx - half, cy + half), (cx - half, cy - half + cut)]
        emit('<polygon points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) +
             f'" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>')

    for name, (ex, ey) in elems.items():
        cx, cy = ex + 85, ey + 85
        rect(ex, ey, 170, 170, "#F3F4F6", col("gr", 2), 2, 4)
        trunc_sq(cx, cy, 64, 16, col("rx", 1), col("rx"))
        trunc_sq(cx, cy, 44, 11, "#FBD3D7", col("tx"))
        text(ex + 8, ey + 164, name, 20, True, INK)

    # TX: от ППМ к АЭ (лево — внешние, зазор — правый столбец)
    tx_routes = [
        (750, 2366, 1440, "АЭ1"), (890, 2348, 1460, "АЭ2"),
        (1030, 2330, 1718, "АЭ3"), (1170, 2312, 1738, "АЭ4"),
    ]
    for cx_, lane, xv, name in tx_routes:
        ex, ey = elems[name]
        py = ey + 85 - 22
        wire([(cx_, IY1 + 8), (cx_, lane), (xv, lane), (xv, py), (ex, py)], "tx", sw=3.5)
        line(ex, py, ex + 60, py, col("tx"), 3)
        dot(ex + 60, py, "tx", 6)
    # RX: от АЭ к ППМ
    rx_routes = [
        ("АЭ4", None, 1960, 2290, 2270), ("АЭ3", None, 1980, 2308, 2410),
        ("АЭ2", (1692, 2870), 2000, 2326, 2550), ("АЭ1", (1672, 2890), 2020, 2344, 2690),
    ]
    for name, via, xv, lane, cx_ in rx_routes:
        ex, ey = elems[name]
        py = ey + 85 + 22
        if via is None:
            pts = [(ex + 170, py), (xv, py)]
        else:
            vx, vy = via
            pts = [(ex + 170, py), (vx, py), (vx, vy), (xv, vy)]
            pts[0] = (ex + 170, py)
        pts += [(xv, lane), (cx_, lane), (cx_, IY1 + 8)]
        if via is not None:
            pts[0] = (ex + 170, py)
        line(ex + 140, py, ex + 170, py, col("rx"), 3)
        dot(ex + 140, py, "rx", 6)
        wire(pts, "rx", sw=3.5)
    # АЭ левого столбца: Rx-порт справа ведём через зазор
    # (линии для АЭ1/АЭ2 начинаются на правой кромке своего элемента)

    # подпись направления стрелок
    text(1500, 2268, "8 × ВЧ к антенне: 4 Tx ↓, 4 Rx ↑", 22, True, INK, "middle")

    # Разрез стекового патча
    text(2170, 2402, "Стековый патч-элемент (разрез)", 26, True, INK)
    text(2170, 2434, "два порта · круговая поляризация", 22, False, MUTED)
    PX0, PX1 = 2230, 2760
    rect(2390, 2520, 210, 12, col("tx"), None, 0, 2)          # Tx-патч
    rect(2260, 2532, 470, 68, "#ECEEF2", "#B5BBC4", 1.5, 0)   # диэлектрик 2
    rect(2330, 2600, 330, 12, col("rx"), None, 0, 2)          # Rx-патч
    rect(2245, 2612, 500, 78, "#ECEEF2", "#B5BBC4", 1.5, 0)   # диэлектрик 1
    rect(PX0, 2690, PX1 - PX0, 16, col("gr", 2), None, 0, 2)  # экран
    # зонды
    rect(2549, 2598, 22, 16, "#ECEEF2", None, 0, 0)           # отверстие в Rx-патче
    line(2560, 2532, 2560, 2706, col("tx"), 5)
    line(2380, 2612, 2380, 2706, col("rx"), 5)
    for x_ in (2380, 2560):
        rect(x_ - 14, 2706, 28, 26, col("gr", 1), col("gr", 2), 2, 2)
    wire([(2560, 2850), (2560, 2734)], "tx", sw=4, halo=None)
    wire([(2380, 2734), (2380, 2850)], "rx", sw=4, halo=None)
    text(2560, 2884, "порт Tx", 22, True, col("tx", 2), "middle")
    text(2560, 2910, "от ППМ", 20, False, col("tx", 2), "middle")
    text(2380, 2884, "порт Rx", 22, True, col("rx", 2), "middle")
    text(2380, 2910, "к ППМ", 20, False, col("rx", 2), "middle")
    # выноски слоёв
    for y_, x_, lab in ((2526, 2600, [("Tx-слой (красный)", col("tx", 2), True),
                                      (" 2170–2200 МГц", INK, False)]),
                        (2606, 2660, [("Rx-слой (синий)", col("rx", 2), True),
                                      (" 1980–2010 МГц", INK, False)]),
                        (2566, 2730, [("диэлектрик", MUTED, False)]),
                        (2650, 2745, [("диэлектрик", MUTED, False)]),
                        (2698, 2760, [("экран (земля)", col("gr", 2), True)])):
        line(x_ + 4, y_, 2790, y_, MUTED, 1.5)
        text(2800, y_ + 8, lab, 22, False, INK, maxw=440)
    # символ круговой поляризации
    emit(f'<path d="M 2470,2503 A 64 18 0 1 1 2545,2502" fill="none" stroke="{INK}" '
         f'stroke-width="3" marker-end="url(#ah-ink-s)"/>')
    text(2580, 2496, "КП", 22, True, INK)

    # ======================================================== SIDE PANEL
    PX, PW = 3370, 770
    rect(PX, 170, PW, 2765, "#FFFFFF", BAND_LINE, 2, 12)
    x = PX + 30

    def h2(y, s):
        text(x, y, s, 32, True, INK)
        line(x, y + 14, PX + PW - 30, y + 14, INK, 2.5)

    h2(228, "Цветовая легенда")
    leg = [
        ("tx", "TX — передача", None),
        ("rx", "RX — приём", None),
        ("pw", "Питание", "27 В, вторичные шины ВИП"),
        ("ct", "Управление и данные", "SPI, LVDS/M-LVDS, CAN, LOAD, PPS"),
        ("gr", "Конструктив, фильтры, разъёмы", "теплоотвод — пунктир"),
    ]
    y = 292
    for kind, a, b in leg:
        wire([(x, y), (x + 100, y)], kind, sw=7, halo=None)
        text(x + 125, y + 10, a, 29, True, col(kind, 2))
        if b:
            text(x + 125, y + 44, b, 23, False, MUTED)
            y += 32
        y += 64

    h2(y + 30, "Сводка параметров")
    y += 76
    kpis = [("4", "луча"), ("396", "АЭ"), ("99", "ППМ"), ("1584", "ВЧ-соединения")]
    for i, (num, lab) in enumerate(kpis):
        kx = x + (i % 2) * 360
        ky = y + (i // 2) * 146
        rect(kx, ky, 345, 132, "#F6F7F9", BAND_LINE, 2, 10)
        text(kx + 22, ky + 74, num, 68, True, INK)
        text(kx + 22, ky + 112, lab, 26, False, MUTED)
    y += 340
    rows = [
        ("Rx (приём)", [("1980–2010 МГц", col("rx", 2), True)]),
        ("Tx (передача)", [("2170–2200 МГц", col("tx", 2), True)]),
        ("Полоса", [("10 МГц", INK, True)]),
        ("ЭИИМ", [("41 дБВт/луч", INK, True)]),
        ("G/T", [("5.6 дБ/К", INK, True)]),
        ("Сканирование", [("±41° (азимут)", INK, True)]),
        ("", [("40° (угол места)", INK, True)]),
        ("Потребление", [("~950–1000 Вт", INK, True)]),
        ("Масса", [("~40–55 кг", INK, True)]),
    ]
    for lab, val in rows:
        if lab:
            line(x, y - 37, PX + PW - 30, y - 37, BAND_LINE, 1.5)
        text(x, y, lab, 27, False, MUTED)
        text(PX + PW - 30, y, val, 29, True, INK, "end")
        y += 54
    h2(y + 36, "Уровни сигнала (на луч)")
    y += 100
    tx_levels = [("ЦАП RFSoC", "≈0 дБм"), ("Драйвер", "+25…+30 дБм"),
                 ("Делитель 1:99", "−24 дБ"), ("Вход ППМ", "≈+1…+6 дБм"),
                 ("GaN УМ, P1dB", "2.5–5 Вт / АЭ")]
    rx_levels = [("GaAs МШУ", "NF < 0.6 дБ"), ("Сумматор 99:1", "+20 дБ (когер.)"),
                 ("Буфер/МШУ", "→ АЦП RFSoC")]
    for title_, kind, lv in (("TX", "tx", tx_levels), ("RX", "rx", rx_levels)):
        text(x, y, title_, 27, True, col(kind, 2))
        y0 = y
        y += 6
        for i, (a, b) in enumerate(lv):
            y += 43
            text(x + 42, y, a, 26, False, INK)
            text(PX + PW - 30, y, b, 26, True, col(kind, 2), "end")
        line(x + 16, y0 + 16, x + 16, y + 2, col(kind), 4)
        emit(f'<polygon points="{x + 7},{y - 4} {x + 25},{y - 4} {x + 16},{y + 12}" '
             f'fill="{col(kind)}"/>')
        y += 62
    h2(y + 10, "Состав ВЧ-соединений")
    y += 66
    for s_ in ["1584 = 99 ППМ × 16 разъёмов", "к сети: 396 Tx + 396 Rx = 792",
               "к антенне: 396 Tx + 396 Rx = 792"]:
        text(x, y, s_, 26, False, INK)
        y += 38
    y += 40
    h2(y, "Обозначения")
    y += 58
    dot(x + 20, y - 9, "ink", 8)
    text(x + 60, y, "разветвление (соединение)", 24, False, INK)
    y += 44
    line(x, y - 9, x + 40, y - 9, INK, 7)
    line(x + 8, y + 5, x + 32, y - 23, INK, 3)
    text(x + 60, y, "шина из N линий", 24, False, INK)
    y += 44
    line(x, y - 9, x + 40, y - 9, INK, 3)
    line(x + 20, y - 28, x + 20, y + 10, "#FFFFFF", 11)
    line(x + 20, y - 28, x + 20, y + 10, INK, 3)
    text(x + 60, y, "пересечение без соединения", 24, False, INK)
    y += 44
    rect(x + 10, y - 24, 26, 22, "#FFFFFF", INK, 2, 3)
    rect(x + 3, y - 31, 26, 22, "#FFFFFF", INK, 2, 3)
    text(x + 60, y, "группа идентичных узлов (×4)", 24, False, INK)
    y += 44
    emit(f'<polygon points="{x + 6},{y - 26} {x + 36},{y - 26} {x + 21},{y + 2}" fill="{INK}"/>')
    text(x + 60, y, "усилитель (вершина — по потоку)", 24, False, INK)
    y += 48
    bpf(x + 21, y - 10, 40, 34)
    text(x + 60, y, "ППФ — полосовой фильтр", 24, False, INK)
    if y > 2915:
        warnings.append(f"side panel overflow y={y}")

    emit("</svg>")


def main():
    build()
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "afar_s_band_d2c.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    for w in warnings:
        print("WARN:", w, file=sys.stderr)
    print(path)


if __name__ == "__main__":
    main()
