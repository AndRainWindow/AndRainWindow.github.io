# AndRainWindow Project Instructions

## Project Overview

This repository contains the AndRainWindow personal website.

The publishing tool (Python Publisher + Tauri desktop GUI) lives in the separate repository:

```text
E:/Documents/D_Dev/Active/PersonPublisher
```

Main stack:

- Astro 7
- Markdown / Astro Content Collections
- GitHub Pages deployment

Main site sections:

- `/` — homepage
- `/photos/` — photography
- `/blog/` — blog

Do not introduce another frontend framework unless it is explicitly required.

---

## Development

Install dependencies with:

```bash
npm install
```

When starting the Astro development server, prefer background mode:

```bash
npx astro dev --background
```

Manage the background server with:

```bash
npx astro dev status
npx astro dev logs
npx astro dev logs --follow
npx astro dev stop
```

Before considering any task complete, run:

```bash
npm run build
```

The Astro build must succeed without errors.

Do not leave an unnecessary foreground dev server running after completing a task.

---

## Project Structure

Important project directories:

```text
src/
├── components/
├── content/
│   └── blog/
├── data/
│   └── photos.json
├── layouts/
└── pages/

public/
└── images/
    ├── blog/
    ├── covers/
    ├── home/
    └── photos/
```

Do not move or rename these directories without a specific reason.

---

## Navigation

The website has only three primary navigation sections:

```text
首页 / 摄影 / 博客
```

All primary pages must reuse:

```text
src/components/SiteNav.astro
```

Do not create separate duplicated navigation implementations for individual pages.

Active navigation states:

```text
homepage          → home
photography       → photos
blog list         → blog
blog article      → blog
```

Keep navigation styling and layout consistent across all pages.

---

## Public Image Paths

Files stored under:

```text
public/images/
```

are served from:

```text
/images/
```

For example:

```text
public/images/blog/example.webp
```

must be referenced as:

```text
/images/blog/example.webp
```

Never use:

```text
public/images/blog/example.webp
```

inside Astro templates, Markdown, JSON, HTML, or CSS.

For dynamic paths that point to files under `public/`, use standard HTML image elements:

```html
<img src="/images/example.webp" alt="Example">
```

Do not pass dynamic `/images/...` strings from `public/` into Astro's `<Image>` component.

---

## Image Format

Web-facing raster images should use WebP whenever practical.

Supported source formats include:

```text
PNG
JPG
JPEG
WEBP
```

Do not automatically convert:

```text
SVG
GIF
ICO
```

GIF files may contain animation and must not be converted unless explicitly requested.

---

## Blog Content

Generated blog entries are stored in:

```text
src/content/blog/
```

These files are generated output.

Do not manually rewrite generated blog content unless debugging a publishing problem.

Publishing metadata currently includes:

```text
title
date
updated
topics
heroImage
wordCount
readingTime
```

Content collection configuration lives in:

```text
src/content.config.ts
```

The blog collection uses a loader.

Do not remove or replace the loader unless required.

---

## Blog Covers

Cover selection priority is:

```text
site_config override
    ↓
first article image
    ↓
default cover
```

Published covers should normally be WebP.

Example:

```yaml
heroImage: "/images/covers/example.webp"
```

Paths stored in configuration must use website paths:

```text
/images/covers/example.webp
```

not:

```text
public/images/covers/example.webp
```

---

## Photography

Photography metadata lives in:

```text
src/data/photos.json
```

Photography files belong in:

```text
public/images/photos/
```

Image references in `photos.json` should use:

```text
/images/photos/example.webp
```

not filesystem paths.

Each row is one photo; rows sharing a `groupId` form a photo group. A group has no separate record: the group title and note are stored on every member row, and the group date is the cover photo's date.

Rows may carry these optional fields:

```text
order                  int, position within the group; 0 is the cover
province/city/district persisted reverse-geocode results
```

`order` is written only for multi-photo groups. `location` stays the composed display string in the form `city · district`.

Raw GPS coordinates are private. They live only in the publishing tool's local state (`.publisher-local/` in the PersonPublisher repository).

Never write raw coordinates into `photos.json` or anywhere else in the public repository.

The homepage/group view uses `displayPhotos()` and keeps groups as contiguous blocks, sorted by cover date descending; members use `order` ascending when all members have it. The `/photos/` timeline uses `buildPhotoTimeline()` and `displayPhotos(records, { sort: 'date' })`: globally sort by EXIF local capture time descending, then aggregate unique year/month/day sections. Do not re-sort already captioned rows, because the group title and note must follow the first visible member in the final display order. Date-only records sort after timed photos that day and never display a fabricated `00:00`; missing or invalid dates appear in an undated section. Never convert capture times through the browser/server timezone.

`PhotoTimelineRings.astro` renders the year/month-day dial and one anchor per date. The page synchronizes it and the right-side metadata as photos scroll. Reserve local images' natural width/height at build time so lazy loading cannot move date targets. The website timeline does not rewrite publisher order or group metadata. Validate changes with `node --test tests/photo-view.test.mjs tests/photo-timeline.test.mjs`, `npm run build`, and `tests/test_photo_timeline_ui.cjs` (Playwright; optionally set `PHOTO_TEST_CHROME`).

The group title and note show on the first visible member only. EXIF renders as two semantic rows:

```text
Camera · Lens
Focal · Aperture · Shutter · ISO
```

The photography page currently follows this structure:

```text
left
→ timeline

center
→ vertically scrolling photography stream

right
→ title, date, location, camera, notes
```

Preserve this layout unless explicitly asked to redesign it.

The homepage photography preview may display recent photographs, but it should use the same `photos.json` data source rather than duplicate metadata.

---

## Styling

The website primarily uses:

```text
Noto Serif SC
```

The current visual language is:

- photography-first
- fixed photographic background
- translucent / glass surfaces
- restrained typography
- relatively minimal navigation
- large photography presentation

Do not introduce unrelated component libraries or design systems without a clear need.

Prefer shared components over duplicated page-specific CSS.

---

## Homepage

The homepage includes:

```text
hero
photography preview
recent blog posts
footer
```

The hero background currently comes from:

```text
/images/home/
```

Large homepage images should be optimized because they directly affect first-load performance.

Do not replace optimized WebP images with large original camera JPEG or PNG files.

---

## GitHub Pages

The site is deployed through GitHub Actions.

Deployment target:

```text
https://AndRainWindow.github.io/
```

Do not add Jekyll build configuration.

GitHub Pages must use the Astro GitHub Actions workflow.

Before deployment-related changes are considered complete, run:

```bash
npm run build
```

---

## Generated Files

Avoid editing generated output when the source of truth exists elsewhere.

Examples:

```text
src/content/blog/
→ generated from Obsidian

public/images/blog/
→ generated by Publisher

public/images/covers/
→ generated by Publisher
```

When a bug appears in generated output, prefer fixing the Publisher rather than manually repairing individual generated files.

---

## Safety for Refactors

When modifying working code:

1. understand the existing implementation first
2. make the smallest reasonable change
3. preserve existing behavior unless the task explicitly changes it
4. avoid rewriting unrelated modules
5. run relevant tests
6. run `npm run build`

Do not perform broad architecture rewrites as a side effect of a small task.

---

## Documentation

Official Astro documentation:

https://docs.astro.build

Consult the relevant Astro documentation before working on:

- routing
- dynamic routes
- middleware
- Astro components
- framework components
- content collections
- styling
- Astro configuration
- deployment

Useful guides:

- Routing  
  https://docs.astro.build/en/guides/routing/

- Astro Components  
  https://docs.astro.build/en/basics/astro-components/

- Content Collections  
  https://docs.astro.build/en/guides/content-collections/

- Styling  
  https://docs.astro.build/en/guides/styling/

Do not replace established project conventions only because a generic Astro example uses a different structure.
