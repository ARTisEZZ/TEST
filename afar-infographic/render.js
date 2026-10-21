// Рендер SVG -> PNG через Chromium (Playwright).
//   node render.js [scale] [out.png]
// scale 2.6 даёт 4992×2808 px — около 300 dpi при печати на ширину A3.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

(async () => {
  const scale = parseFloat(process.argv[2] || '2.6');
  const out = process.argv[3] || path.join(__dirname, 'afar_exploded_view.png');
  const svg = fs.readFileSync(path.join(__dirname, 'afar_exploded_view.svg'), 'utf8');
  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: scale,
  });
  await page.setContent(
    `<!doctype html><html><head><meta charset="utf-8">` +
      `<style>html,body{margin:0;padding:0;background:#fff}svg{display:block}</style>` +
      `</head><body>${svg}</body></html>`,
    { waitUntil: 'load' }
  );
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: out, clip: { x: 0, y: 0, width: 1920, height: 1080 } });
  await browser.close();
  console.log(`rendered ${out} @${scale}x`);
})();
