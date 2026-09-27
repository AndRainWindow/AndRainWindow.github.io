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

// Group members run earliest-capture-first. Compare the validated day, then the
// time: a date-only record has no time, so it trails the timed photos of its own
// day (matching the timeline), and a row with no usable date goes last rather
// than quietly sorting as midnight. Plain code-unit comparison, because
// localeCompare orders punctuation before digits.
function byEarliestCapture(a, b) {
  const left = photoDateParts(a.date);
  const right = photoDateParts(b.date);
  if (!left.sortKey || !right.sortKey) {
    return left.sortKey === right.sortKey ? 0 : (left.sortKey ? -1 : 1);
  }
  if (left.day !== right.day) return left.day < right.day ? -1 : 1;
  if (!left.time || !right.time) {
    return left.time === right.time ? 0 : (left.time ? -1 : 1);
  }
  return left.sortKey === right.sortKey ? 0 : (left.sortKey < right.sortKey ? -1 : 1);
}

// Timeline order: newest capture day first, earliest capture first within each
// day, so a day section still reads chronologically. A row with no usable date
// keeps company with the other undated rows at the end.
function byDayThenEarliestCapture(a, b) {
  const left = photoDateParts(a.date);
  const right = photoDateParts(b.date);
  if (left.day === right.day) return byEarliestCapture(a, b);
  return right.day < left.day ? -1 : 1;
}

// A group the publisher arranged by hand carries `manualOrder` on its members
// and displays in that saved sequence, so `order: 0` leads it and the chosen
// cover comes first. Every other group runs earliest-capture-first. This mirrors
// the publisher's own orderedMembers(); a member whose order is missing trails.
function orderedGroupMembers(members) {
  if (members.some(photo => photo.manualOrder === true)) {
    const saved = photo => (Number.isInteger(photo.order) ? photo.order : Number.MAX_SAFE_INTEGER);
    return [...members].sort((a, b) => saved(a) - saved(b));
  }
  return [...members].sort(byEarliestCapture);
}

// Homepage/group views order members as above. The photography timeline opts
// into date ordering BEFORE applying the first-visible-member captions.
export function displayPhotos(records, { sort = 'group' } = {}) {
  const visible = records.filter(p => !p.hidden && !p.deleted && !p.groupHidden && !p.groupDeleted);
  let photos;
  if (sort === 'date') {
    photos = [...visible].sort(byDayThenEarliestCapture);
  } else {
    // Group-contiguous blocks (key = groupId || id, insertion order preserved):
    // a block's first photo is its cover, which dates the block. Blocks
    // interleave never.
    const blocks = new Map();
    for (const photo of visible) {
      const key = photo.groupId || photo.id;
      if (!blocks.has(key)) blocks.set(key, []);
      blocks.get(key).push(photo);
    }
    const ordered = [...blocks.values()]
      .map(members => {
        const block = orderedGroupMembers(members);
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
