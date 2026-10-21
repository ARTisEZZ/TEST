# Структурная схема 4-лучевой АФАР S-диапазона (Direct-to-Cell)

| Файл | Назначение |
|---|---|
| `afar_s_band_d2c.png` | растр A3, 300 dpi (4961 × 3508 px) |
| `afar_s_band_d2c.pdf` | вектор A3, альбомная ориентация, для печати |
| `afar_s_band_d2c.svg` | исходный вектор (правится в Inkscape / Illustrator) |
| `build_diagram.py` | генератор SVG (все координаты и подписи) |
| `render.js` | рендер SVG → PNG + PDF (Playwright/Chromium) |

Пересборка:

```bash
python3 build_diagram.py && node render.js
```
