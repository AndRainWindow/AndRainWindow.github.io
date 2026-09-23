import { displayPhotos } from './photo-view.mjs';

// Derived view only: keep photos.json and publisher group order untouched.
export function photoDayId(day) {
  return `photo-day-${day || 'undated'}`;
}

export function buildPhotoTimeline(records) {
  const photos = displayPhotos(records, { sort: 'date' });

  const years = new Map();

  for (const photo of photos) {
    const year = photo.day.slice(0, 4);

    if (!years.has(year)) years.set(year, new Map());
    const months = years.get(year);

    const monthKey = photo.day.slice(0, 7);
    if (!months.has(monthKey)) months.set(monthKey, new Map());

    const days = months.get(monthKey);
    const dayKey = photo.day;
    if (!days.has(dayKey)) days.set(dayKey, []);

    days.get(dayKey).push(photo);
  }

  return [...years.entries()].map(([year, months]) => ({
    year,
    months: [...months.entries()].map(([month, days]) => ({
      month,
      days: [...days.entries()].map(([day, items]) => ({
        day,
        id: photoDayId(day),
        items,
      })),
    })),
  }));
}
