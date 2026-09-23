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
