// Shared by the photography stream and homepage; no changes to the site layout.
export function displayPhotos(records) {
  const visible = records.filter(p => !p.hidden && !p.deleted && !p.groupHidden && !p.groupDeleted);
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
  const seen = new Set();
  return ordered.flatMap(({ block }) => block.map(photo => {
    const group = photo.groupId || photo.id;
    const first = !seen.has(group);
    seen.add(group);
    const title = photo.title || (first ? photo.groupTitle || '' : '');
    const note = photo.note || (first ? photo.groupNote || '' : '');
    // EXIF local wall time: never parse through Date or fabricate midnight.
    const time = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(photo.date) ? photo.date.slice(11, 16) : '';
    const equip = [photo.camera, photo.lens].filter(Boolean).join(' · ');
    const exposure = [photo.focalLength && `${photo.focalLength}mm`,
      photo.aperture && `f/${photo.aperture}`,
      photo.shutter && `${photo.shutter}s`,
      photo.iso && `ISO ${photo.iso}`].filter(Boolean).join(' · ');
    // Kept for compatibility; identical output to the previous single join.
    const cameraDetails = [equip, exposure].filter(Boolean).join(' · ');
    return { ...photo, title, note, time, equip, exposure, cameraDetails, alt: title || photo.groupTitle || '摄影作品' };
  }));
}
