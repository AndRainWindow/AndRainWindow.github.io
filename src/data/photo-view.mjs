// Shared by the photography stream and homepage; no changes to the site layout.
export function displayPhotos(records) {
  const visible = records.filter(p => !p.hidden && !p.deleted && !p.groupHidden && !p.groupDeleted);
  visible.sort((a, b) => String(b.date).localeCompare(String(a.date)));
  const seen = new Set();
  return visible.map(photo => {
    const group = photo.groupId || photo.id;
    const first = !seen.has(group);
    seen.add(group);
    const title = photo.title || (first ? photo.groupTitle || '' : '');
    const note = photo.note || (first ? photo.groupNote || '' : '');
    const time = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(photo.date) ? photo.date.slice(11, 16) : '';
    const cameraDetails = [photo.camera, photo.lens,
      photo.focalLength && `${photo.focalLength}mm`,
      photo.aperture && `f/${photo.aperture}`,
      photo.shutter && `${photo.shutter}s`,
      photo.iso && `ISO ${photo.iso}`].filter(Boolean).join(' · ');
    return { ...photo, title, note, time, cameraDetails, alt: title || photo.groupTitle || '摄影作品' };
  });
}
