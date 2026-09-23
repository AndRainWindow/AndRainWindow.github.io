import test from 'node:test';
import assert from 'node:assert/strict';
import { buildPhotoTimeline, photoDayId } from '../src/data/photo-timeline.mjs';
import { displayPhotos } from '../src/data/photo-view.mjs';

const flattenDays = timeline => timeline.flatMap(year => year.months.flatMap(month => month.days));
const rows = records => flattenDays(buildPhotoTimeline(records)).flatMap(day => day.items);
const group = { groupId: 'trip', groupTitle: '旅行', groupNote: '整组感受', title: '', note: '' };

test('timeline merges dates across groups and ignores manual order, without changing gallery order', () => {
  const input = [
    { ...group, id: 'morning', date: '2026-09-23T09:12', order: 0 },
    { id: 'other', groupId: 'other', date: '2026-09-23T16:20' },
    { ...group, id: 'evening', date: '2026-09-23T18:35', order: 1 },
    { ...group, id: 'yesterday', date: '2026-09-22T21:05', order: 2 },
    { id: 'next-year', date: '2027-01-01T00:00' },
  ];
  const original = structuredClone(input);
  const days = flattenDays(buildPhotoTimeline(input));
  assert.deepEqual(days.map(d => d.day), ['2027-01-01', '2026-09-23', '2026-09-22']);
  assert.deepEqual(days[1].items.map(p => p.id), ['evening', 'other', 'morning']);
  assert.equal(days[1].items[0].title, '旅行');
  assert.equal(days[1].items[2].title, '');
  assert.equal(days[2].items[0].note, '');
  assert.deepEqual(displayPhotos(input).map(p => p.id), ['next-year', 'other', 'morning', 'evening', 'yesterday']);
  assert.deepEqual(input, original);
});

test('captions follow the first visible chronological member; per-photo overrides survive', () => {
  const input = [
    { ...group, id: 'early', date: '2026-09-23T09:00', order: 0 },
    { ...group, id: 'late', date: '2026-09-23T19:00', order: 1 },
    { ...group, id: 'custom', date: '2026-09-23T18:00', title: '单张标题', note: '单张感受' },
    { ...group, id: 'hidden', date: '2026-09-24', hidden: true },
    { id: 'deleted', date: '2026-09-25', deleted: true },
    { id: 'group-hidden', date: '2026-09-26', groupHidden: true },
    { id: 'group-deleted', date: '2026-09-27', groupDeleted: true },
  ];
  assert.deepEqual(rows(input).map(p => [p.id, p.title, p.note]), [
    ['late', '旅行', '整组感受'], ['custom', '单张标题', '单张感受'], ['early', '', ''],
  ]);
  input[1].hidden = true;
  input[2].deleted = true;
  assert.deepEqual(rows(input).map(p => [p.id, p.title, p.note]), [['early', '旅行', '整组感受']]);
});

test('wall-clock sorting keeps seconds, ignores timezone conversion, and never invents midnight', () => {
  const input = [
    { id: 'legacy', date: '2026-09-23' },
    { id: 'utc', date: '2026-09-23T18:35:29Z' },
    { id: 'local', date: '2026-09-23T18:35:30+08:00' },
    { id: 'offset', date: '2026-09-23T18:00:00-05:00' },
    { id: 'midnight', date: '2026-09-23T00:00' },
    { id: 'space', date: '2026-09-23 18:35:30.01' },
  ];
  assert.deepEqual(rows(input).map(p => [p.id, p.time]), [
    ['space', '18:35'], ['local', '18:35'], ['utc', '18:35'], ['offset', '18:00'], ['midnight', '00:00'], ['legacy', ''],
  ]);
});

test('equal capture times have stable source order', () => {
  const input = ['b', 'a', 'c'].map(id => ({ id, date: '2026-09-23T12:30' }));
  assert.deepEqual(rows(input).map(p => p.id), ['b', 'a', 'c']);
});

test('missing or invalid dates remain visible in an undated bucket, after real dates', () => {
  const input = [
    { id: 'missing' }, { id: 'invalid', date: '2026-02-30' }, { id: 'empty', date: '' },
    { id: 'leap', date: '2024-02-29' }, { id: 'not-leap', date: '2025-02-29' },
    { id: 'time-invalid', date: '2026-09-23T28:00' },
  ];
  const days = flattenDays(buildPhotoTimeline(input));
  assert.deepEqual(days.map(day => day.day), ['2024-02-29', '']);
  assert.equal(days[1].id, photoDayId(''));
  assert.equal(days[1].items.length, 5);
  assert.ok(days[1].items.every(p => p.time === ''));
});

test('an empty or entirely hidden collection has no phantom dates', () => {
  assert.deepEqual(buildPhotoTimeline([]), []);
  assert.deepEqual(buildPhotoTimeline([{ id: 'hidden', date: '2026-09-23', hidden: true }]), []);
});
