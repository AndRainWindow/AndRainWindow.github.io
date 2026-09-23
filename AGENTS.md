# AndRainWindow Project Instructions

## Project Overview

This repository contains the AndRainWindow personal website.

Main stack:

- Astro 7
- Markdown / Astro Content Collections
- Python-based Obsidian publishing tool
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

publisher/
├── parsers/
├── processors/
├── migration/
└── gui/
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

## WebP Processing

WebP conversion logic must live in one reusable module:

```text
publisher/processors/webp.py
```

Do not duplicate WebP conversion code inside:

```text
article.py
cover.py
image.py
GUI code
migration code
```

Other modules should call the shared WebP processor.

Recommended presets:

```text
blog
max width: 2000 px
quality: 82

cover
max width: 1600 px
quality: 80

photo
max width: 2560 px
quality: 85

hero
max width: 2560 px
quality: 82
```

Image conversion must:

- preserve transparency where appropriate
- apply EXIF orientation correction
- preserve aspect ratio
- avoid unnecessary upscaling
- avoid repeatedly recompressing unchanged images
- output `.webp` filenames without double extensions

Correct:

```text
photo.webp
```

Incorrect:

```text
photo.jpg.webp
```

---

## Obsidian Publisher

The publishing pipeline is:

```text
Obsidian Vault
    ↓
Python Publisher
    ↓
src/content/blog/
public/images/blog/
public/images/covers/
    ↓
Astro
```

The Publisher has already been modularized.

Do not redesign or collapse the existing Publisher architecture unless explicitly requested.

Extend the existing architecture instead.

---

## Publisher Architecture

Keep responsibilities separated.

Expected structure:

```text
publisher/
├── config.py
├── publisher.py
├── parsers/
│   ├── metadata.py
│   └── images.py
├── processors/
│   ├── article.py
│   ├── image.py
│   ├── cover.py
│   ├── stats.py
│   └── webp.py
├── migration/
│   └── webp_migrator.py
└── gui/
```

General responsibilities:

```text
parsers/
→ parse content and metadata

processors/
→ transform content and files

publisher.py
→ coordinate publishing

migration/
→ one-time or bulk migrations

gui/
→ user interface only
```

Do not put parsing, image conversion, or publishing logic directly into the GUI.

---

## Obsidian Image Syntax

The Publisher must continue supporting:

```md
![[image.png]]
```

and:

```md
![[image.png|668]]
```

The second form means:

```text
image filename = image.png
display width = 668
```

The width value is not part of the filename.

Never generate invalid URLs such as:

```text
/images/blog/image.png|668
```

Instead, a width-constrained image may be rendered as:

```html
<img
    src="/images/blog/image.webp"
    alt="image.webp"
    width="668"
>
```

---

## Markdown Images

The Publisher must also support normal Markdown images:

```md
![alt](image.jpg)
```

Local relative images should be copied or converted into the appropriate public image directory and rewritten to root-relative URLs.

Correct:

```md
![alt](/images/blog/image.webp)
```

Do not leave article-local relative URLs such as:

```text
image.jpg
```

because browsers may resolve them as:

```text
/blog/article-slug/image.jpg
```

which causes incorrect Astro route requests and 404 errors.

---

## Raw HTML Images

The Publisher must support raw HTML images such as:

```html
<img src="image.jpg" width="680">
```

Local images should be converted and rewritten to:

```html
<img src="/images/blog/image.webp" width="680">
```

Image captions must remain unchanged.

Example:

```html
<img src="/images/blog/image.webp" width="680">

<p class="img-caption">
    Caption text
</p>
```

The Publisher must not remove or rewrite caption content unless explicitly requested.

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

Raw GPS coordinates are private. They live only in:

```text
.publisher-local/sources.json
```

Never write raw coordinates into `photos.json` or anywhere else in the public repository.

`locationSource` may be:

```text
geoapify
amap
```

Reverse geocoding supports both providers, selected in the desktop app settings. AMap receives GCJ02-converted coordinates (WGS84 → GCJ02 conversion for mainland China, no-op elsewhere), and the AMap key stays in `.publisher-local`, never in the frontend bundle. The public page credits the active provider (Geoapify / 高德地图) in its footer.

Reverse geocoding runs during import and per photo on demand, never at public render time. Import batches one request per distinct rounded coordinate and caches results in:

```text
.publisher-local/geocode-cache.json
```

Cache keys are provider-prefixed:

```text
provider:lat,lon
```

Legacy cache keys without a prefix remain valid Geoapify entries.

Import rules:

- a single-photo import does not require a group title; 2 or more photos require one
- photos are imported in capture time ascending order and the first photo is the cover
- unreferenced generated `photo-<32 hex>.webp` files under `public/images/photos/` are swept at import start and at preview start

The `photos` CLI command emits N `photo_progress` JSONL lines followed by exactly one terminal line (`photo_result` or `error`). This is the CLI contract.

`update-group` supports:

```text
order      explicit member photo id list; rewrites every member's order
cover      moves the chosen photo to position 0
noteToAll  writes the group note into every member's own note field
```

`noteToAll` is an explicit one-click action, not an automatic copy. Member notes stay independently editable afterwards.

The public gallery renders groups as contiguous blocks. Blocks are sorted by cover date descending. Within a block, members are ordered by `order` ascending when all members have `order`, and fall back to date descending otherwise.

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

## Image Migration

Existing raster images under:

```text
public/images/
```

may be migrated to WebP.

The migration process must follow this order:

```text
1. Generate WebP files
2. Update local project references
3. Keep original JPG/PNG files
4. Run npm run build
5. Verify image paths
6. Only then allow removal of old files
```

Do not delete original JPG, JPEG, or PNG files during the first migration pass.

---

## Reference Migration

When updating image references, inspect relevant project files such as:

```text
src/**/*.astro
src/**/*.md
src/**/*.mdx
src/**/*.json
src/**/*.css
src/**/*.ts
src/**/*.js
site_config.json
```

Only update local website image references.

Examples of paths that may be rewritten:

```text
/images/home/hero.jpg
/images/blog/example.png
public/images/covers/example.jpg
```

Do not rewrite external URLs such as:

```text
https://example.com/image.jpg
https://github.com/example/image.png
```

---

## Migration Reporting

Bulk WebP migration should create a report such as:

```text
migration_report.json
```

The report should include:

- converted images
- skipped images
- source paths
- destination paths
- original sizes
- new sizes
- files whose references were updated
- errors

This report should make migration behavior auditable and easier to reverse.

---

## Publisher GUI

The Publisher GUI is a thin interface over the Publisher core.

It may provide:

```text
Obsidian Vault selection
Astro project selection
Publish Blog button
Migrate Images to WebP button
Progress bar
Current task
Log view
```

Long-running work must not block the GUI thread.

Use a worker thread and a queue or equivalent mechanism.

The GUI must not independently implement:

```text
Markdown parsing
attachment lookup
WebP conversion
cover generation
publishing logic
```

It should call the existing Publisher APIs.

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
