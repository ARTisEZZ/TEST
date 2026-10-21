// Рендер SVG-схемы в PNG (A3, 300 dpi) и векторный PDF (A3 landscape) через Playwright.
//   node render.js [file.svg]
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

(async () => {
  const svgPath = path.resolve(process.argv[2] || path.join(__dirname, 'afar_s_band_d2c.svg'));
  const base = svgPath.replace(/\.svg$/, '');
  const svg = fs.readFileSync(svgPath, 'utf8');
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    @page { size: 420mm 297mm; margin: 0; }
    html, body { margin: 0; padding: 0; background: #fff; }
    svg { display: block; width: 420mm; height: 297mm; }
  </style></head><body>${svg}</body></html>`;

  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' }).catch(() => chromium.launch());
  const page = await browser.newPage({ viewport: { width: 4200, height: 2970 }, deviceScaleFactor: 1 });

  // PNG: 4961 × 3508 px (A3 @ 300 dpi)
  const pngHtml = html.replace('width: 420mm; height: 297mm;', 'width: 4961px; height: 3508px;');
  await page.setViewportSize({ width: 4961, height: 3508 });
  await page.setContent(pngHtml, { waitUntil: 'load' });
  await page.screenshot({ path: `${base}.png`, clip: { x: 0, y: 0, width: 4961, height: 3508 } });

  // PDF: вектор, A3 альбомная
  await page.setContent(html, { waitUntil: 'load' });
  await page.pdf({ path: `${base}.pdf`, width: '420mm', height: '297mm', printBackground: true, pageRanges: '1' });

  await browser.close();
  console.log(`${base}.png\n${base}.pdf`);
})();
