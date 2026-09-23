// Build a chronological timeline from EXIF-based photo timestamps.
// This is separate from displayPhotos(): gallery ordering and timeline ordering
// have different purposes.

export function buildPhotoTimeline(records) {
  const photos = records
    .filter((p) => !p.hidden && !p.deleted && !p.groupHidden && !p.groupDeleted)
    .filter((p) => typeof p.date === 'string')
    .map((p) => ({
      ...p,
      time: /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(p.date)
        ? p.date.slice(11, 16)
        : '',
    }))
    .sort((a, b) => String(b.date).localeCompare(String(a.date)));

  const years = new Map();

  for (const photo of photos) {
    const [year, month, day] = photo.date.slice(0, 10).split('-');

    if (!years.has(year)) years.set(year, new Map());
    const months = years.get(year);

    const monthKey = `${year}-${month}`;
    if (!months.has(monthKey)) months.set(monthKey, new Map());

    const days = months.get(monthKey);
    const dayKey = `${year}-${month}-${day}`;
    if (!days.has(dayKey)) days.set(dayKey, []);

    days.get(dayKey).push(photo);
  }

  return [...years.entries()].map(([year, months]) => ({
    year,
    months: [...months.entries()].map(([month, days]) => ({
      month,
      days: [...days.entries()].map(([day, items]) => ({
        day,
        items: items.sort((a, b) => String(b.date).localeCompare(String(a.date))),
      })),
    })),
  }));
}
