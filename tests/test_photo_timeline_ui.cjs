// Run after npm run build. Requires Playwright and a Chrome executable.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');

const root = path.resolve(__dirname, '..', 'dist');
const artifacts = process.env.PHOTO_UI_ARTIFACTS || path.join(require('node:os').tmpdir(), 'photo-timeline-ui');
fs.mkdirSync(artifacts, { recursive: true });
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.webp': 'image/webp', '.woff': 'font/woff', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  let name = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  if (name.endsWith('/')) name += 'index.html';
  const file = path.resolve(root, '.' + name);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
  res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
  fs.createReadStream(file).pipe(res);
});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${server.address().port}/photos/`;
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PHOTO_TEST_CHROME || undefined,
    args: ['--no-sandbox'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    const dayLinks = await page.locator('.timeline-link').evaluateAll(links => links.map(link => ({ day: link.dataset.day, count: Number(link.dataset.count), hash: link.getAttribute('href') })));
    assert.equal(new Set(dayLinks.map(link => link.day)).size, dayLinks.length, 'dates must not repeat');
    assert.equal(await page.locator('.photo-day').count(), dayLinks.length);
    const ids = await page.locator('.photo-item').evaluateAll(items => items.map(item => item.id));
    assert.equal(new Set(ids).size, ids.length, 'photo anchors must be unique');
    const dates = await page.locator('.photo-item').evaluateAll(items => items.map(item => JSON.parse(item.dataset.photo).date));
    assert.deepEqual(dates, [...dates].sort().reverse(), 'photographs must descend by capture time');
    assert.ok(await page.locator('.photo-frame img').evaluateAll(images => images.every(image => Number(image.getAttribute('width')) > 0 && Number(image.getAttribute('height')) > 0)), 'lazy images need reserved geometry');
    await page.screenshot({ path: path.join(artifacts, 'desktop.png') });

    for (const day of dayLinks) {
      await page.locator(`.timeline-link[data-day="${day.day}"]`).click();
      await page.waitForFunction(day => document.querySelector('[data-timeline-day]').value === day, day.day);
      const section = page.locator(day.hash);
      assert.equal(await section.locator('.photo-item').count(), day.count);
      const photo = await section.locator('.photo-item').first().getAttribute('data-photo').then(JSON.parse);
      await page.waitForFunction(expected => document.querySelector('#info-date').textContent === expected, [photo.time, photo.location].filter(Boolean).join(' · '));
      assert.equal(await page.locator('#info-equip').textContent(), photo.equip);
      assert.equal(await page.locator('#info-title').textContent(), photo.title);
      assert.equal(await page.locator('#info-note').textContent(), photo.note);
      assert.equal(await page.locator('.timeline-link[aria-current="date"]').count(), 1);
    }

    // Native controls, browser history, and existing photo deep links.
    if (dayLinks.length) {
      const first = dayLinks[0], last = dayLinks.at(-1);
      await page.getByLabel('选择年份').selectOption(first.day.slice(0, 4));
      await page.getByLabel('选择月日').selectOption(first.day);
      await page.waitForFunction(day => document.querySelector('.timeline-link.active').dataset.day === day, first.day);
      await page.locator(`.timeline-link[data-day="${last.day}"]`).click();
      await page.waitForFunction(day => document.querySelector('.timeline-link.active').dataset.day === day, last.day);
      await page.goBack();
      await page.waitForFunction(day => document.querySelector('.timeline-link.active').dataset.day === day, first.day);
    }
    if (ids.length > 1) {
      const id = ids[Math.floor(ids.length / 2)];
      await page.goto(url + '#' + id);
      const target = await page.locator('#' + id).getAttribute('data-photo').then(JSON.parse);
      await page.waitForFunction(expected => document.querySelector('#info-date').textContent === expected, [target.time, target.location].filter(Boolean).join(' · '));
      await page.mouse.wheel(0, 650);
      await page.waitForTimeout(250);
      const inReadingPosition = await page.locator('.photo-item').evaluateAll(items => {
        const anchor = Math.min(innerHeight * .34, 260);
        const item = items.filter(item => item.getBoundingClientRect().top <= anchor).at(-1) || items[0];
        const data = JSON.parse(item.dataset.photo);
        return { time: [data.time, data.location].filter(Boolean).join(' · '), day: item.dataset.day, position: item.dataset.dayPosition };
      });
      assert.equal(await page.locator('#info-date').textContent(), inReadingPosition.time);
      assert.equal(await page.locator('.timeline-link.active').getAttribute('data-day'), inReadingPosition.day);
      await page.screenshot({ path: path.join(artifacts, 'desktop-scrolled.png') });
    }

    for (const width of [820, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(url);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `overflow at ${width}px`);
      if (width === 390) {
        assert.equal(await page.locator('.photo-info').isVisible(), false);
        assert.equal(await page.locator('[data-timeline]').isVisible(), true);
        assert.equal(await page.locator('.mobile-info').first().isVisible(), true);
      }
      await page.screenshot({ path: path.join(artifacts, `width-${width}.png`) });
    }
    assert.deepEqual(errors, [], 'no page script errors');
    console.log(JSON.stringify({ ok: true, photos: ids.length, days: dayLinks.length, viewports: [1440, 820, 390] }));
  } finally {
    await browser.close();
    server.close();
  }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
