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
    const entryLinks = await page.locator('.timeline-link').evaluateAll(links => links.map(link => ({
      key: link.dataset.entry, year: link.dataset.year, label: link.dataset.label,
      count: Number(link.dataset.count), hash: link.getAttribute('href'),
    })));
    assert.equal(new Set(entryLinks.map(link => link.key)).size, entryLinks.length, 'entry keys must not repeat');
    assert.equal(await page.locator('.photo-entry').count(), entryLinks.length);
    const ids = await page.locator('.photo-item').evaluateAll(items => items.map(item => item.id));
    assert.equal(new Set(ids).size, ids.length, 'photo anchors must be unique');
    const rows = await page.locator('.photo-item').evaluateAll(items => items.map(item => {
      const photo = JSON.parse(item.dataset.photo);
      return { entry: item.dataset.entry, day: photo.day, time: photo.time };
    }));
    // Entry covers run newest-first with the undated bucket last; inside one
    // entry the days run earliest-first (a multi-day group ascends), and timed
    // photos lead the date-only ones of their day.
    const dayDesc = (a, b) => {
      if (!a) return b ? 1 : 0;
      if (!b) return -1;
      return a < b ? 1 : a > b ? -1 : 0;
    };
    const dayAsc = (a, b) => {
      if (!a) return b ? 1 : 0;
      if (!b) return -1;
      return a < b ? -1 : a > b ? 1 : 0;
    };
    const covers = entryLinks.map(link => rows.find(row => row.entry === link.key)?.day ?? '');
    assert.deepEqual(covers, [...covers].sort(dayDesc), 'entry covers must descend');
    for (const link of entryLinks) {
      const members = rows.filter(row => row.entry === link.key);
      const days = members.map(row => row.day);
      assert.deepEqual(days, [...days].sort(dayAsc), `days must ascend inside ${link.label || link.key}`);
      for (const day of [...new Set(days)]) {
        const seq = members.filter(row => row.day === day).map(row => row.time);
        assert.deepEqual(seq, [...seq.filter(Boolean)].sort().concat(seq.filter(time => !time)),
          `timed photos ascend and date-only trail inside ${day || 'the undated day'}`);
      }
    }
    assert.ok(await page.locator('.photo-frame img').evaluateAll(images => images.every(image => Number(image.getAttribute('width')) > 0 && Number(image.getAttribute('height')) > 0)), 'lazy images need reserved geometry');
    await page.locator('.photo-frame img').first().evaluate(image => image.decode());
    await page.screenshot({ path: path.join(artifacts, 'desktop.png') });

    // Homepage covers deep-link to entry sections that exist on /photos/.
    const base = url.replace(/photos\/$/, '');
    await page.goto(base);
    const homeHrefs = await page.locator('.timeline-item').evaluateAll(items => items.map(item => item.getAttribute('href')));
    assert.ok(homeHrefs.length > 0 && homeHrefs.every(href => /^\/photos\/#photo-entry-/.test(href)), 'covers link to entry hashes');
    assert.equal(await page.locator('.photo-more').getAttribute('href'), '/photos/');
    await page.goto(url);
    const dangling = await page.evaluate(hrefs => hrefs.filter(href => !document.getElementById(href.split('#')[1])), homeHrefs);
    assert.deepEqual(dangling, [], 'every cover hash must resolve to an element on /photos/');

    // Mobile taps must navigate too: the strip only suppresses clicks after a
    // real mouse drag, never on touch.
    const touchPage = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    try {
      await touchPage.goto(base);
      await touchPage.locator('.timeline-item').first().tap();
      await touchPage.waitForURL(/\/photos\/#photo-entry-/);
      const tappedHash = await touchPage.evaluate(() => location.hash);
      assert.ok(await touchPage.evaluate(id => !!document.getElementById(id), tappedHash.slice(1)),
        'tapped cover hash resolves on mobile');
    } finally {
      await touchPage.close();
    }

    // Portrait frames narrow below the column, stay centered, and respect the height cap.
    const portraitBox = await page.locator('.photo-item').evaluateAll(items => {
      for (const item of items) {
        const img = item.querySelector('.photo-frame img');
        const w = Number(img.getAttribute('width')), h = Number(img.getAttribute('height'));
        if (h > w) {
          const frame = item.querySelector('.photo-frame').getBoundingClientRect();
          const box = item.getBoundingClientRect();
          return { id: item.id, width: frame.width, itemWidth: box.width, left: frame.left - box.left, right: box.right - frame.right, height: frame.height, viewport: innerHeight };
        }
      }
      return null;
    });
    if (portraitBox) {
      assert.ok(portraitBox.width < portraitBox.itemWidth - 1, 'portrait frames narrow below the column');
      assert.ok(Math.abs(portraitBox.left - portraitBox.right) <= 2, 'portrait frames stay centered in the column');
      assert.ok(portraitBox.height <= portraitBox.viewport * 0.78 + 6, 'portrait frame respects max height');
      // The info panel slides beside the centered portrait and widens into the gap.
      await page.goto(url + '#' + portraitBox.id);
      await page.waitForTimeout(300);
      const placement = await page.evaluate(id => {
        const frame = document.getElementById(id).querySelector('.photo-frame').getBoundingClientRect();
        const panel = document.querySelector('.photo-info').getBoundingClientRect();
        return { gap: panel.left - frame.right, width: panel.width };
      }, portraitBox.id);
      assert.ok(placement.gap >= 25 && placement.gap <= 55, `info panel sits beside the centered portrait (gap ${placement.gap})`);
      assert.ok(placement.width > 300, `info panel widens to absorb the freed space (width ${placement.width})`);
    }

    for (const link of entryLinks) {
      await page.locator(`.timeline-link[data-entry="${link.key}"]`).click();
      await page.waitForFunction(key => document.querySelector('.timeline-link.active')?.dataset.entry === key, link.key);
      const section = page.locator(link.hash);
      assert.equal(await section.locator('.photo-item').count(), link.count);
      const photo = await section.locator('.photo-item').first().getAttribute('data-photo').then(JSON.parse);
      await page.waitForFunction(expected => document.querySelector('#info-date').textContent === expected, [photo.time, photo.location].filter(Boolean).join(' · '));
      assert.equal(await page.locator('#info-equip').textContent(), photo.equip);
      assert.equal(await page.locator('#info-title').textContent(), photo.title);
      assert.equal(await page.locator('#info-note').textContent(), photo.note);
      assert.equal(await page.locator('.timeline-link[aria-current="true"]').count(), 1);
    }

    // Native controls, browser history, and existing photo deep links.
    if (entryLinks.length) {
      const first = entryLinks[0], last = entryLinks.at(-1);
      const firstDay = rows.find(row => row.entry === first.key && row.day)?.day;
      const lastDay = rows.filter(row => row.entry === last.key && row.day).at(-1)?.day;
      await page.getByLabel('选择年份').selectOption(first.year);
      // The day dial jumps to the day's first photo; history restores the hop.
      await page.getByLabel('选择月日').selectOption(firstDay);
      await page.waitForFunction(key => document.querySelector('.timeline-link.active').dataset.entry === key, first.key);
      await page.getByLabel('选择月日').selectOption(lastDay);
      await page.waitForFunction(key => document.querySelector('.timeline-link.active').dataset.entry === key, last.key);
      await page.goBack();
      await page.waitForFunction(key => document.querySelector('.timeline-link.active').dataset.entry === key, first.key);
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
        return { time: [data.time, data.location].filter(Boolean).join(' · '), entry: item.dataset.entry, day: data.day };
      });
      assert.equal(await page.locator('#info-date').textContent(), inReadingPosition.time);
      assert.equal(await page.locator('.timeline-link.active').getAttribute('data-entry'), inReadingPosition.entry);
      if (inReadingPosition.day) {
        assert.equal(await page.locator('[data-timeline-day]').inputValue(), inReadingPosition.day,
          'dial follows the scrolled photo day');
      }
      await page.screenshot({ path: path.join(artifacts, 'desktop-scrolled.png') });
    }

    // The day-change hairline carries that day's MM.DD on the line itself;
    // no line above the very first photo, and undated changes stay unlabeled.
    const marks = await page.locator('.photo-item').evaluateAll(items => items.map((item, index) => {
      const photo = JSON.parse(item.dataset.photo);
      const previous = item.previousElementSibling;
      const hasBreak = !!previous?.classList.contains('day-break');
      return {
        index,
        hasBreak,
        breakText: hasBreak ? previous.textContent.trim() : null,
        expectBreak: Boolean(photo.dayStart && index > 0),
        expectDate: photo.dayStart && index > 0 && photo.day ? photo.day.slice(5).replace('-', '.') : '',
      };
    }));
    for (const mark of marks) {
      assert.equal(mark.hasBreak, mark.expectBreak, `hairlines mark day changes except at the top (${mark.index})`);
      if (mark.hasBreak) assert.equal(mark.breakText, mark.expectDate, `hairline labels read MM.DD (${mark.index})`);
    }

    // The dial lists every distinct day run as MM.DD; it follows the scrolled
    // photo's own day rather than pinning to the entry's first day.
    const dialOptions = await page.locator('[data-timeline-day] option').evaluateAll(options =>
      options.map(option => ({ day: option.value, text: option.textContent })));
    const streamDays = [...new Set(rows.map(row => row.day).filter(Boolean))];
    assert.deepEqual([...new Set(dialOptions.map(option => option.day))].sort(), [...streamDays].sort(),
      'dial lists one option per distinct day');
    for (const option of dialOptions) {
      assert.equal(option.text, option.day.slice(5).replace('-', '.'), `dial options read MM.DD (${option.day})`);
    }

    // Month labels head one run of same-month entries, in list order.
    const archiveMonths = await page.locator('.archive-month').allTextContents();
    const linkMonths = await page.locator('.timeline-link').evaluateAll(links => links.map(link => link.dataset.month));
    const monthRuns = linkMonths.filter((month, index) => index === 0 || month !== linkMonths[index - 1])
      .filter(month => month !== 'undated');
    assert.deepEqual(monthRuns.map(month => `${Number(month)}月`), archiveMonths, 'each month label heads one month run');

    for (const width of [820, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(url);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `overflow at ${width}px`);
      if (width === 390) {
        assert.equal(await page.locator('.photo-info').isVisible(), false);
        assert.equal(await page.locator('[data-timeline]').isVisible(), true);
        assert.equal(await page.locator('.mobile-info').first().isVisible(), true);
        assert.ok(await page.locator('.photo-frame').first().evaluate(frame => {
          const w = frame.getBoundingClientRect().width;
          return Math.abs(w - frame.parentElement.getBoundingClientRect().width) <= 2;
        }), 'mobile frames stay full width');
      }
      await page.locator('.photo-frame img').first().evaluate(image => image.decode());
      await page.screenshot({ path: path.join(artifacts, `width-${width}.png`) });
    }
    assert.deepEqual(errors, [], 'no page script errors');
    console.log(JSON.stringify({ ok: true, photos: ids.length, entries: entryLinks.length, viewports: [1440, 820, 390] }));
  } finally {
    await browser.close();
    server.close();
  }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
