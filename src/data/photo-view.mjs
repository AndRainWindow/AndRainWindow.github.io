// Capture dates are local wall-clock values. Do not convert EXIF offsets to UTC.
export function photoDateParts(value) {
  const match = typeof value === 'string' && value.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ]([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d)(?:\.(\d+))?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/);
  if (!match) return { day: '', time: '', sortKey: '' };
  const [, year, month, day, hour, minute, second = '00', fraction = ''] = match;
  const y = Number(year);
  const days = [31, y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (Number(day) < 1 || Number(day) > (days[Number(month) - 1] || 0)) {
    return { day: '', time: '', sortKey: '' };
  }
  const date = `${year}-${month}-${day}`;
  const time = hour === undefined ? '' : `${hour}:${minute}`;
  return { day: date, time, sortKey: time ? `${date}T${time}:${second}.${fraction.padEnd(9, '0')}` : date };
}

// Homepage/group views keep their manual ordering. The photography timeline
// opts into date ordering BEFORE applying the first-visible-member captions.
export function displayPhotos(records, { sort = 'group' } = {}) {
  const visible = records.filter(p => !p.hidden && !p.deleted && !p.groupHidden && !p.groupDeleted);
  let photos;
  if (sort === 'date') {
    photos = visible
      .map(photo => ({ photo, key: photoDateParts(photo.date).sortKey }))
      .sort((a, b) => b.key.localeCompare(a.key))
      .map(({ photo }) => photo);
  } else {
    // Group-contiguous blocks (key = groupId || id, insertion order preserved):
    // within a block, every member carrying an integer order -> order asc;
    // otherwise the legacy date-desc behaviour. Blocks interleave never.
    const blocks = new Map();
    for (const photo of visible) {
      const key = photo.groupId || photo.id;
      if (!blocks.has(key)) blocks.set(key, []);
      blocks.get(key).push(photo);
    }
    const ordered = [...blocks.values()]
      .map(members => {
        const block = members.every(p => Number.isInteger(p.order))
          ? [...members].sort((a, b) => a.order - b.order)
          : [...members].sort((a, b) => String(b.date).localeCompare(String(a.date)));
        // Block position = the cover (first photo of the block) date.
        return { block, coverDate: String(block[0].date) };
      })
      .sort((a, b) => b.coverDate.localeCompare(a.coverDate));
    photos = ordered.flatMap(({ block }) => block);
  }
  const seen = new Set();
  return photos.map(photo => {
    const group = photo.groupId || photo.id;
    const first = !seen.has(group);
    seen.add(group);
    const title = photo.title || (first ? photo.groupTitle || '' : '');
    const note = photo.note || (first ? photo.groupNote || '' : '');
    // EXIF local wall time: never parse through Date or fabricate midnight.
    const { day, time } = photoDateParts(photo.date);
    const equip = [photo.camera, photo.lens].filter(Boolean).join(' · ');
    const exposure = [photo.focalLength && `${photo.focalLength}mm`,
      photo.aperture && `f/${photo.aperture}`,
      photo.shutter && `${photo.shutter}s`,
      photo.iso && `ISO ${photo.iso}`].filter(Boolean).join(' · ');
    // Kept for compatibility; identical output to the previous single join.
    const cameraDetails = [equip, exposure].filter(Boolean).join(' · ');
    return { ...photo, title, note, day, time, equip, exposure, cameraDetails, alt: title || photo.groupTitle || '摄影作品' };
  });
}
