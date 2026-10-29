import test from 'node:test';
import assert from 'node:assert/strict';
import { buildPhotoTimeline, photoEntryId } from '../src/data/photo-timeline.mjs';
import { displayPhotos } from '../src/data/photo-view.mjs';

const flattenEntries = timeline => timeline.flatMap(year => year.entries);
const rows = records => flattenEntries(buildPhotoTimeline(records)).flatMap(entry => entry.items);
const group = { groupId: 'trip', groupTitle: '旅行', groupNote: '整组感受', title: '', note: '' };

test('timeline keeps one entry per group across days and ignores manual order, without changing gallery order', () => {
  const input = [
    { ...group, id: 'morning', date: '2026-09-23T09:12', order: 0 },
    { id: 'other', groupId: 'other', date: '2026-09-23T16:20' },
    { ...group, id: 'evening', date: '2026-09-23T18:35', order: 1 },
    { ...group, id: 'yesterday', date: '2026-09-22T21:05', order: 2 },
    { id: 'next-year', date: '2027-01-01T00:00' },
  ];
  const original = structuredClone(input);
  const entries = flattenEntries(buildPhotoTimeline(input));
  // Entries run newest-cover-first; the trip group is ONE entry dated by its
  // earliest capture (09-22), so it sits below the 09-23 'other' entry.
  assert.deepEqual(entries.map(e => e.key), ['day-2027-01-01', 'other', 'trip']);
  assert.deepEqual(entries.map(e => e.label), ['01.01', '09.23', '旅行']);
  // Month comes from the cover day and runs newest-first, so same-month
  // entries stay adjacent for the index's month labels.
  assert.deepEqual(entries.map(e => [e.key, e.month]), [
    ['day-2027-01-01', '01'], ['other', '09'], ['trip', '09'],
  ]);
  // Inside the entry the photos run earliest-capture-first across days.
  assert.deepEqual(entries[2].items.map(p => p.id), ['yesterday', 'morning', 'evening']);
  // Captions follow the first visible member of that final order.
  assert.equal(entries[2].items[0].title, '旅行');
  assert.equal(entries[2].items[0].note, '整组感受');
  assert.equal(entries[2].items[1].title, '');
  // dayStart marks the first photo of each day run in flat stream order, even
  // when the day sequence zigzags because a group ascends out of order.
  assert.deepEqual(rows(input).map(p => [p.id, !!p.dayStart]), [
    ['next-year', true], ['other', true], ['yesterday', true], ['morning', true], ['evening', false],
  ]);
  // Group view: blocks contiguous, each block earliest-capture-first.
  assert.deepEqual(displayPhotos(input).map(p => p.id), ['next-year', 'other', 'yesterday', 'morning', 'evening']);
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
    ['early', '旅行', '整组感受'], ['custom', '单张标题', '单张感受'], ['late', '', ''],
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
  // All rows are ungrouped and share one day, so they form one day bucket.
  const entries = flattenEntries(buildPhotoTimeline(input));
  assert.deepEqual(entries.map(e => e.key), ['day-2026-09-23']);
  assert.deepEqual(entries[0].items.map(p => [p.id, p.time]), [
    ['midnight', '00:00'], ['offset', '18:00'], ['utc', '18:35'], ['local', '18:35'], ['space', '18:35'], ['legacy', ''],
  ]);
});

test('equal capture times have stable source order', () => {
  const input = ['b', 'a', 'c'].map(id => ({ id, date: '2026-09-23T12:30' }));
  assert.deepEqual(rows(input).map(p => p.id), ['b', 'a', 'c']);
});

test('missing or invalid dates remain visible in an undated entry, after real dates', () => {
  const input = [
    { id: 'missing' }, { id: 'invalid', date: '2026-02-30' }, { id: 'empty', date: '' },
    { id: 'leap', date: '2024-02-29' }, { id: 'not-leap', date: '2025-02-29' },
    { id: 'time-invalid', date: '2026-09-23T28:00' },
  ];
  const entries = flattenEntries(buildPhotoTimeline(input));
  assert.deepEqual(entries.map(entry => [entry.key, entry.day, entry.month, entry.label]), [
    ['day-2024-02-29', '2024-02-29', '02', '02.29'],
    ['day-undated', '', '', '日期未知'],
  ]);
  assert.equal(entries[1].id, photoEntryId('day-undated'));
  assert.equal(entries[1].items.length, 5);
  assert.ok(entries[1].items.every(p => p.time === ''));
});

test('an empty or entirely hidden collection has no phantom dates', () => {
  assert.deepEqual(buildPhotoTimeline([]), []);
  assert.deepEqual(buildPhotoTimeline([{ id: 'hidden', date: '2026-09-23', hidden: true }]), []);
});

test('a multi-day group stays one entry in capture order, manualOrder ignored', () => {
  const input = [
    { ...group, id: 'd2', date: '2026-06-29T10:00', order: 1, manualOrder: true },
    { ...group, id: 'd1', date: '2026-06-28T07:00', order: 0, manualOrder: true },
    { id: 'solo', date: '2026-06-27' },
  ];
  const entries = flattenEntries(buildPhotoTimeline(input));
  assert.deepEqual(entries.map(e => [e.key, e.day, e.month, e.label, e.items.length]), [
    ['trip', '2026-06-28', '06', '旅行', 2],
    ['day-2026-06-27', '2026-06-27', '06', '06.27', 1],
  ]);
  assert.equal(entries[0].id, photoEntryId('trip'));
  // Capture order wins over the saved manual order on the timeline.
  assert.deepEqual(entries[0].items.map(p => p.id), ['d1', 'd2']);
  // The 06-29 member marks the mid-entry day change for the tag/hairline.
  assert.deepEqual(rows(input).map(p => [p.id, !!p.dayStart]), [
    ['d1', true], ['d2', true], ['solo', true],
  ]);
});

test('two groups sharing a day stay separate entries with unique anchors', () => {
  const input = [
    { id: 'a1', groupId: 'g1', groupTitle: '甲', date: '2026-06-27T09:00' },
    { id: 'b1', groupId: 'g2', groupTitle: '乙', date: '2026-06-27T08:00' },
  ];
  const entries = flattenEntries(buildPhotoTimeline(input));
  // Same cover day: the earlier cover leads.
  assert.deepEqual(entries.map(e => e.key), ['g2', 'g1']);
  assert.deepEqual(entries.map(e => e.label), ['乙', '甲']);
  assert.equal(new Set(entries.map(e => e.id)).size, 2);
  // One day run: only the first photo carries the day tag, no hairline between.
  assert.deepEqual(rows(input).map(p => [p.id, !!p.dayStart]), [['b1', true], ['a1', false]]);
});

test('day changes into and out of the undated run mark tags and hairlines', () => {
  const input = [
    { ...group, id: 'dated', date: '2026-06-27T10:00' },
    { ...group, id: 'unknown' },
    { id: 'solo', date: '2026-06-26' },
  ];
  const entries = flattenEntries(buildPhotoTimeline(input));
  assert.deepEqual(entries.map(e => e.key), ['trip', 'day-2026-06-26']);
  // Undated members trail inside their entry.
  assert.deepEqual(entries[0].items.map(p => p.id), ['dated', 'unknown']);
  // dated('2026-06-27') → unknown('') → solo('2026-06-26'): every change counts.
  assert.deepEqual(rows(input).map(p => [p.id, !!p.dayStart]), [
    ['dated', true], ['unknown', true], ['solo', true],
  ]);
});

test('entry labels fall back from group title to date to 日期未知', () => {
  const input = [
    { groupId: 'g1', groupTitle: '', title: '', note: '', id: 'untitled', date: '2026-06-27T10:00' },
    { id: 'solo', date: '2026-06-26' },
    { groupId: 'g2', groupTitle: '夜色', title: '', note: '', id: 'night' },
    { groupId: 'g3', groupTitle: '', title: '', note: '', id: 'lost' },
  ];
  const entries = flattenEntries(buildPhotoTimeline(input));
  assert.deepEqual(entries.map(e => [e.key, e.label]), [
    ['g1', '06.27'], ['day-2026-06-26', '06.26'], ['g2', '夜色'], ['g3', '日期未知'],
  ]);
});
