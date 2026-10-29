import { displayPhotos, photoEntryKey } from './photo-view.mjs';

export { photoEntryKey };

// Derived view only: keep photos.json and publisher group order untouched.
export function photoEntryId(key) {
  return `photo-entry-${key}`;
}

export function buildPhotoTimeline(records) {
  const photos = displayPhotos(records, { sort: 'date' });

  // dayStart marks the first photo of each distinct-day run in flat stream
  // order (crossing entry boundaries); the page uses it for MM.DD tags and
  // hairlines. Written onto the enriched copies, never onto photos.json rows.
  for (let i = 0; i < photos.length; i++) {
    photos[i].dayStart = i === 0 || photos[i].day !== photos[i - 1].day;
  }

  const entries = new Map();
  for (const photo of photos) {
    const key = photoEntryKey(photo);
    if (!entries.has(key)) entries.set(key, []);
    entries.get(key).push(photo);
  }

  const years = new Map();
  for (const [key, items] of entries) {
    const day = items[0].day;
    const year = day.slice(0, 4);
    const month = day.slice(5, 7);
    const label = items.find(photo => photo.groupTitle)?.groupTitle
      || (day ? day.slice(5).replace('-', '.') : '日期未知');
    if (!years.has(year)) years.set(year, []);
    years.get(year).push({ key, id: photoEntryId(key), day, month, label, items });
  }

  return [...years.entries()].map(([year, entries]) => ({ year, entries }));
}
