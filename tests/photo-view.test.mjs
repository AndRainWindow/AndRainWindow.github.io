import test from 'node:test';
import assert from 'node:assert/strict';
import { displayPhotos } from '../src/data/photo-view.mjs';

const group = { groupId: 'trip', groupTitle: '海边', groupNote: '蓝调时刻', title: '', note: '' };
test('group text appears only on the first visible image; times keep EXIF wall-clock minutes', () => {
  const data = [{ ...group, id: 'a', date: '2026-09-23T17:42' }, { ...group, id: 'b', date: '2026-09-23T17:40' }];
  let rows = displayPhotos(data);
  assert.equal(rows[0].title, '海边'); assert.equal(rows[0].time, '17:42');
  assert.equal(rows[1].title, ''); assert.equal(rows[1].note, '');
  data[0].hidden = true;
  rows = displayPhotos(data);
  assert.equal(rows[0].id, 'b'); assert.equal(rows[0].note, '蓝调时刻');
});
test('per-photo overrides, deleted/hidden groups and legacy dates', () => {
  const rows = displayPhotos([
    { ...group, id: 'a', date: '2026-09-23T17:42' },
    { ...group, id: 'b', date: '2026-09-23T17:40', title: '单张标题', note: '单张感受' },
    { id: 'c', date: '2026-09-22', title: '旧照片', camera: 'Sony' },
    { id: 'd', date: '2026-09-24', deleted: true },
    { id: 'e', date: '2026-09-24', groupHidden: true },
    { id: 'f', date: '2026-09-24', groupDeleted: true },
  ]);
  assert.equal(rows.length, 3); assert.equal(rows[1].title, '单张标题');
  assert.equal(rows[1].note, '单张感受'); assert.equal(rows[2].time, '');
});
test('members with an integer order render order-asc inside their group', () => {
  const rows = displayPhotos([
    { ...group, id: 'c', date: '2026-05-03T10:00', order: 2 },
    { ...group, id: 'a', date: '2026-05-01T09:00', order: 0 },
    { ...group, id: 'b', date: '2026-05-02T08:00', order: 1 },
  ]);
  assert.deepEqual(rows.map(p => p.id), ['a', 'b', 'c']);
  assert.equal(rows[0].title, '海边');
});
test('any member without order falls the whole group back to date desc', () => {
  const rows = displayPhotos([
    { ...group, id: 'a', date: '2026-05-01T09:00', order: 0 },
    { ...group, id: 'c', date: '2026-05-03T10:00', order: 2 },
    { ...group, id: 'b', date: '2026-05-02T08:00' },
  ]);
  assert.deepEqual(rows.map(p => p.id), ['c', 'b', 'a']);
});
test('group members stay contiguous even when dates interleave with another group', () => {
  const rows = displayPhotos([
    { id: 'a2', groupId: 'g', groupTitle: '组', date: '2026-09-21T08:00' },
    { id: 'x', date: '2026-09-22' },
    { id: 'a1', groupId: 'g', groupTitle: '组', date: '2026-09-23T17:42' },
  ]);
  assert.deepEqual(rows.map(p => p.id), ['a1', 'a2', 'x']);
});
test('blocks sort by cover date desc, not by newest member', () => {
  const rows = displayPhotos([
    { ...group, id: 'cover', date: '2026-09-01T08:00', order: 0 },
    { ...group, id: 'newer', date: '2026-06-20T18:00', order: 1 },
    { id: 'solo', date: '2026-09-10' },
  ]);
  assert.deepEqual(rows.map(p => p.id), ['solo', 'cover', 'newer']);
});
test('deleted cover lets the next visible member carry group title/note', () => {
  const rows = displayPhotos([
    { ...group, id: 'cover', date: '2026-09-23T17:42', order: 0, deleted: true },
    { ...group, id: 'member', date: '2026-09-23T17:40', order: 1 },
  ]);
  assert.deepEqual(rows.map(p => p.id), ['member']);
  assert.equal(rows[0].title, '海边');
  assert.equal(rows[0].note, '蓝调时刻');
});
test('equip and exposure split the EXIF into two lines; lens and time are optional', () => {
  const full = displayPhotos([{ id: 'a', date: '2026-09-23T17:42',
    camera: 'Sony ZV-E10', lens: 'Viltrox 25mm F1.7 E',
    focalLength: '25', aperture: '6.3', shutter: '1/500', iso: '100' }])[0];
  assert.equal(full.equip, 'Sony ZV-E10 · Viltrox 25mm F1.7 E');
  assert.equal(full.exposure, '25mm · f/6.3 · 1/500s · ISO 100');

  const noLens = displayPhotos([{ id: 'b', date: '2026-09-22',
    camera: 'Sony ZV-E10', focalLength: '25', aperture: '6.3', shutter: '1/500', iso: '100' }])[0];
  assert.equal(noLens.equip, 'Sony ZV-E10');
  assert.equal(noLens.exposure, '25mm · f/6.3 · 1/500s · ISO 100');
  assert.equal(noLens.time, '');
});
test('cameraDetails output stays byte-identical for legacy rows', () => {
  const rows = displayPhotos([{
    id: 'photo-legacy', title: '', note: '', date: '2026-02-08T16:25',
    camera: 'SONY ZV-E10', lens: 'Viltrox 25mm F1.7 E',
    iso: '100', aperture: '6.3', shutter: '1/500', focalLength: '25',
  }]);
  assert.equal(rows[0].cameraDetails, 'SONY ZV-E10 · Viltrox 25mm F1.7 E · 25mm · f/6.3 · 1/500s · ISO 100');
  assert.equal(rows[0].equip, 'SONY ZV-E10 · Viltrox 25mm F1.7 E');
  assert.equal(rows[0].exposure, '25mm · f/6.3 · 1/500s · ISO 100');

  const cameraOnly = displayPhotos([{ id: 'c', date: '2026-09-22', camera: 'Sony' }])[0];
  assert.equal(cameraOnly.cameraDetails, 'Sony');
});
