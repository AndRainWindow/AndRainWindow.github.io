import json
import subprocess
import tempfile
import os
import io
import urllib.error
import urllib.request
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageCms
from publisher.photos.catalog import PhotoCatalog, atomic_json, project_lock
from publisher.photos.coord import out_of_china, wgs84_to_gcj02
from publisher.photos.metadata import inspect_photo
from publisher.photos.service import dispatch
from publisher.photos import publish as publishing
from publisher.photos import geocode


def make_photo(path: Path, date: str = '2026:09:23 17:42:59',
               gps: dict | None = None) -> dict:
    exif = Image.Exif()
    exif[271] = 'Sony'; exif[272] = 'ILCE-6700'
    exif[0x8769] = {36867: date, 42036: '56mm F1.7', 34855: 400,
                    33437: 1.7, 33434: .004, 37386: 56}
    if gps:
        exif[0x8825] = gps
    Image.new('RGB', (600, 400), 'navy').save(path, exif=exif)
    return inspect_photo(str(path))


class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'site'
        self.root.mkdir()
        (self.root / 'package.json').write_text('{}')
        self.catalog = PhotoCatalog(self.root)
        atomic_json(self.catalog.path, [])
        self.source = Path(self.tmp.name) / '原始照片.jpg'
        exif = Image.Exif()
        exif[271] = 'Sony'; exif[272] = 'ILCE-6700'
        exif[0x8769] = {36867: '2026:09:23 17:42:59', 42036: '56mm F1.7',
                         34855: 400, 33437: 1.7, 33434: .004, 37386: 56}
        exif[0x8825] = {1: 'N', 2: (40, 47, 0), 3: 'W', 4: (73, 58, 0)}
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        Image.new('RGB', (2800, 1400), 'navy').save(self.source, exif=exif, icc_profile=profile)

    def tearDown(self):
        self.tmp.cleanup()

    def import_one(self):
        photo = inspect_photo(str(self.source))
        return dispatch(self.root, {'action': 'import', 'title': '纽约', 'note': '散步', 'photos': [photo]})['photos'][0]

    def test_exif_minutes_and_webp_only_without_gps(self):
        metadata = inspect_photo(str(self.source))
        self.assertEqual(metadata['date'], '2026-09-23T17:42')
        self.assertEqual(metadata['shutter'], '1/250')
        self.assertEqual(metadata['iso'], '400')
        self.assertAlmostEqual(metadata['gps']['lat'], 40.783333, places=5)
        original = self.source.read_bytes()
        row = self.import_one()
        self.assertEqual(row['title'], '')
        self.assertEqual(row['groupNote'], '散步')
        public = json.loads(self.catalog.path.read_text(encoding='utf-8'))
        self.assertNotIn('gps', public[0]); self.assertNotIn('source', public[0])
        output = self.root / 'public' / row['image'].lstrip('/')
        with Image.open(output) as image:
            self.assertEqual(image.format, 'WEBP'); self.assertEqual(image.width, 2560)
            self.assertFalse(image.getexif()); self.assertTrue(image.info.get('icc_profile'))
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(list(self.root.rglob('*.jpg')))
        self.import_one()
        self.assertEqual(len(self.catalog.load()), 1)

    def test_missing_date_is_not_invented_and_invalid_batch_does_not_write(self):
        plain = Path(self.tmp.name) / 'plain.jpg'
        Image.new('RGB', (50, 50)).save(plain)
        item = inspect_photo(str(plain))
        self.assertEqual(item['date'], '')
        before = self.catalog.path.read_bytes()
        with self.assertRaises(ValueError):
            dispatch(self.root, {'action': 'import', 'title': '组', 'photos': [inspect_photo(str(self.source)), item]})
        self.assertEqual(self.catalog.path.read_bytes(), before)
        self.assertFalse(list(self.root.rglob('*.webp')))

    def test_edit_hide_restore_and_group_state_are_independent(self):
        row = self.import_one()
        dispatch(self.root, {'action': 'update', 'id': row['id'], 'changes': {'title': '独立', 'hidden': True}})
        dispatch(self.root, {'action': 'update-group', 'id': row['groupId'], 'changes': {'groupDeleted': True}})
        dispatch(self.root, {'action': 'update-group', 'id': row['groupId'], 'changes': {'groupDeleted': False}})
        saved = self.catalog.load()[0]
        self.assertTrue(saved['hidden']); self.assertFalse(saved['groupDeleted'])
        self.assertEqual(saved['title'], '独立')
        self.assertTrue((self.root / 'public' / saved['image'].lstrip('/')).exists())

    def test_os_lock_blocks_another_writer(self):
        with project_lock(self.root):
            with self.assertRaises(ValueError):
                with project_lock(self.root): pass

    def test_geocode_only_exports_city_and_county_and_caches(self):
        dispatch(self.root, {'action': 'geo-preferences', 'apiKey': 'test-key'})
        response = json.dumps({'results': [{'city': '纽约', 'county': '纽约县', 'street': '私有地址', 'housenumber': '19'}]}).encode()
        import io
        with patch.object(geocode.urllib.request, 'urlopen', return_value=io.BytesIO(response)) as request:
            result = dispatch(self.root, {'action': 'geocode', 'source': str(self.source)})
            self.assertEqual(result['location'], '纽约 · 纽约县')
            again = dispatch(self.root, {'action': 'geocode', 'source': str(self.source)})
            self.assertEqual(result, again); self.assertEqual(request.call_count, 1)


class ImportPipelineTests(unittest.TestCase):
    """Multi-photo import: progress, ordering, cover, note-to-all, orphan sweep."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'site'; self.root.mkdir()
        (self.root / 'package.json').write_text('{}')
        self.catalog = PhotoCatalog(self.root)
        atomic_json(self.catalog.path, [])

    def tearDown(self): self.tmp.cleanup()

    def import_photos(self, dates, on_event=None, **payload):
        photos = []
        for index, date in enumerate(dates):
            photos.append(make_photo(Path(self.tmp.name) / f'p{index}.jpg', date=date))
        payload.setdefault('title', '整组')
        payload['photos'] = photos
        return dispatch(self.root, {'action': 'import', **payload}, on_event)

    def test_single_photo_import_allows_empty_group_title(self):
        result = self.import_photos(['2026:09:23 10:00:00'], title='')
        row = result['photos'][0]
        self.assertEqual(row['groupTitle'], '')
        with self.assertRaisesRegex(ValueError, '整组标题'):
            self.import_photos(['2026:09:23 10:00:00', '2026:09:23 10:01:00'], title='')

    def test_import_emits_ordered_progress_events(self):
        events = []
        result = self.import_photos(['2026:09:23 10:00:00', '2026:09:23 10:01:00'],
                                    taskId='task-1', on_event=events.append)
        self.assertEqual([e['phase'] for e in events],
                         ['inspect', 'inspect', 'convert', 'convert', 'finalize'])
        self.assertTrue(all(e['taskId'] == 'task-1' for e in events))
        for phase in ('inspect', 'convert'):
            current = [e['current'] for e in events if e['phase'] == phase]
            self.assertEqual(current, [1, 2])

    def test_import_writes_capture_time_order_and_cover_is_first(self):
        self.import_photos(['2026:09:23 10:02:00', '2026:09:23 10:00:00',
                            '2026:09:23 10:01:00'])
        saved = {p['date']: p for p in self.catalog.load()}
        orders = sorted(p['order'] for p in saved.values())
        self.assertEqual(orders, [0, 1, 2])
        first = min(saved.values(), key=lambda p: p['order'])
        self.assertEqual(first['date'], '2026-09-23T10:00')

    def test_update_group_order_cover_and_note_to_all(self):
        self.import_photos(['2026:09:23 10:00:00', '2026:09:23 10:01:00',
                            '2026:09:23 10:02:00'])
        rows = sorted(self.catalog.load(), key=lambda p: p['order'])
        group_id = rows[0]['groupId']
        new_order = [rows[2]['id'], rows[0]['id'], rows[1]['id']]
        dispatch(self.root, {'action': 'update-group', 'id': group_id, 'order': new_order,
                             'changes': {'groupTitle': '整组', 'groupNote': ''}})
        saved = {p['id']: p for p in self.catalog.load()}
        self.assertEqual([saved[pid]['order'] for pid in new_order], [0, 1, 2])
        with self.assertRaisesRegex(ValueError, '组成员不一致'):
            dispatch(self.root, {'action': 'update-group', 'id': group_id,
                                 'order': ['bogus'], 'changes': {}})
        dispatch(self.root, {'action': 'update-group', 'id': group_id, 'cover': rows[1]['id'],
                             'changes': {'groupTitle': '整组', 'groupNote': ''}})
        saved = {p['id']: p for p in self.catalog.load()}
        self.assertEqual(saved[rows[1]['id']]['order'], 0)
        dispatch(self.root, {'action': 'update-group', 'id': group_id,
                             'changes': {'groupTitle': '整组', 'groupNote': '共享感受'},
                             'noteToAll': True})
        for row in self.catalog.load():
            self.assertEqual(row['note'], '共享感受')
            self.assertEqual(row['groupNote'], '共享感受')

    def test_sweep_orphans_clears_dead_webp_and_keeps_referenced_and_manual(self):
        self.catalog.output.mkdir(parents=True)
        orphan = self.catalog.output / f'photo-{"a" * 32}.webp'; orphan.write_bytes(b'x')
        manual = self.catalog.output / 'manual.webp'; manual.write_bytes(b'x')
        self.import_photos(['2026:09:23 10:00:00'])
        self.assertFalse(orphan.exists())
        self.assertTrue(manual.exists())
        kept = self.catalog.load()[0]['image']
        self.assertTrue((self.root / 'public' / kept.lstrip('/')).exists())


class GeocodeProviderTests(unittest.TestCase):
    """Provider selection, AMap lookups, batch dedupe, and cache compatibility."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'site'; self.root.mkdir()
        (self.root / 'package.json').write_text('{}')
        self.catalog = PhotoCatalog(self.root)
        atomic_json(self.catalog.path, [])
        self.gps_ny = {1: 'N', 2: (40, 47, 0), 3: 'W', 4: (73, 58, 0)}
        self.source = Path(self.tmp.name) / '原始照片.jpg'
        make_photo(self.source, gps=self.gps_ny)

    def tearDown(self): self.tmp.cleanup()

    def test_wgs84_to_gcj02_known_shift_and_overseas_passthrough(self):
        lat, lon = wgs84_to_gcj02(39.90733, 116.39123)
        self.assertGreater(lon - 116.39123, 0.004)
        self.assertLess(lon - 116.39123, 0.009)
        self.assertGreater(lat - 39.90733, 0.0005)
        self.assertLess(lat - 39.90733, 0.003)
        self.assertEqual(wgs84_to_gcj02(40.78, -73.97), (40.78, -73.97))
        self.assertTrue(out_of_china(40.78, -73.97))
        self.assertFalse(out_of_china(39.90733, 116.39123))

    def test_amap_lookup_success(self):
        dispatch(self.root, {'action': 'geo-preferences', 'provider': 'amap', 'amapKey': 'amap-key'})
        response = json.dumps({'status': '1',
                               'regeocode': {'addressComponent': {
                                   'province': '浙江省', 'city': '宁波市', 'district': '宁海县'}}}).encode()
        with patch.object(geocode.urllib.request, 'urlopen', return_value=io.BytesIO(response)) as request:
            result = dispatch(self.root, {'action': 'geocode', 'source': str(self.source)})
        self.assertEqual(result['location'], '宁波市 · 宁海县')
        self.assertEqual(result['locationSource'], 'amap')
        self.assertEqual((result['province'], result['city'], result['district']),
                         ('浙江省', '宁波市', '宁海县'))
        requested = request.call_args[0][0].full_url
        self.assertIn('restapi.amap.com/v3/geocode/regeo', requested)
        # Overseas coordinates pass through unchanged (no GCJ02 shift applied).
        self.assertIn('location=-73.966667', requested)

    def test_amap_municipality_empty_city_falls_back_to_province(self):
        dispatch(self.root, {'action': 'geo-preferences', 'provider': 'amap', 'amapKey': 'amap-key'})
        response = json.dumps({'status': '1',
                               'regeocode': {'addressComponent': {
                                   'province': '北京市', 'city': [], 'district': '朝阳区'}}}).encode()
        with patch.object(geocode.urllib.request, 'urlopen', return_value=io.BytesIO(response)):
            result = dispatch(self.root, {'action': 'geocode', 'source': str(self.source)})
        self.assertEqual(result['location'], '北京市 · 朝阳区')

    def test_amap_missing_key_and_request_failure(self):
        dispatch(self.root, {'action': 'geo-preferences', 'provider': 'amap'})
        with self.assertRaisesRegex(ValueError, '高德'):
            dispatch(self.root, {'action': 'geocode', 'source': str(self.source)})
        dispatch(self.root, {'action': 'geo-preferences', 'amapKey': 'bad'})
        with patch.object(geocode.urllib.request, 'urlopen',
                          return_value=io.BytesIO(b'{"status":"0","info":"INVALID_USER_KEY"}')):
            with self.assertRaisesRegex(ValueError, 'Key 无效'):
                dispatch(self.root, {'action': 'geocode', 'source': str(self.source)})

    def test_import_batch_geocode_dedupes_and_survives_failure(self):
        dispatch(self.root, {'action': 'geo-preferences', 'provider': 'amap', 'amapKey': 'amap-key'})
        same_a = make_photo(Path(self.tmp.name) / 'a.jpg', '2026:09:23 10:00:00',
                            gps={1: 'N', 2: (40, 47, 0), 3: 'W', 4: (73, 58, 0)})
        same_b = make_photo(Path(self.tmp.name) / 'b.jpg', '2026:09:23 10:01:00',
                            gps={1: 'N', 2: (40, 47, 0), 3: 'W', 4: (73, 58, 0)})
        other = make_photo(Path(self.tmp.name) / 'c.jpg', '2026:09:23 10:02:00',
                           gps={1: 'N', 2: (41, 0, 0), 3: 'W', 4: (74, 0, 0)})
        good = json.dumps({'status': '1', 'regeocode': {'addressComponent': {
            'province': '纽约州', 'city': '纽约市', 'district': '曼哈顿'}}}).encode()
        calls = []
        def fake_urlopen(request, timeout=0):
            calls.append(request.full_url)
            if len(calls) == 1:
                return io.BytesIO(good)
            raise urllib.error.URLError('network down')
        with patch.object(geocode.urllib.request, 'urlopen', side_effect=fake_urlopen):
            result = dispatch(self.root, {'action': 'import', 'title': '整组',
                                          'photos': [same_a, same_b, other]})
        self.assertEqual(len(calls), 2)  # two distinct coords, one shared
        located = [p for p in self.catalog.load() if p.get('location')]
        self.assertEqual(len(located), 2)
        for row in located:
            self.assertEqual(row['location'], '纽约市 · 曼哈顿')
            self.assertEqual(row['locationSource'], 'amap')
            self.assertEqual(row['city'], '纽约市')
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('地点识别失败', result['message'])

    def test_cache_supports_legacy_geoapify_keys_and_isolates_providers(self):
        gps = inspect_photo(str(self.source))['gps']
        legacy_key = f"{gps['lat']:.5f},{gps['lon']:.5f}"
        atomic_json(self.catalog.local / 'geocode-cache.json',
                    {legacy_key: {'location': '缓存地点', 'locationSource': 'geoapify'}})
        dispatch(self.root, {'action': 'geo-preferences', 'apiKey': 'g-key'})
        def boom(*args, **kwargs):
            raise AssertionError('cache must prevent HTTP calls')
        with patch.object(geocode.urllib.request, 'urlopen', side_effect=boom):
            result = dispatch(self.root, {'action': 'geocode', 'source': str(self.source)})
        self.assertEqual(result['location'], '缓存地点')
        # Same coordinates under the amap provider must NOT hit the geoapify entry.
        dispatch(self.root, {'action': 'geo-preferences', 'provider': 'amap', 'amapKey': 'a-key'})
        response = json.dumps({'status': '1', 'regeocode': {'addressComponent': {
            'province': '纽约州', 'city': '纽约市', 'district': ''}}}).encode()
        with patch.object(geocode.urllib.request, 'urlopen', return_value=io.BytesIO(response)) as request:
            amap_result = dispatch(self.root, {'action': 'geocode', 'source': str(self.source)})
        self.assertEqual(request.call_count, 1)
        self.assertEqual(amap_result['location'], '纽约市')


class GitPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'work'; self.root.mkdir()
        self.remote = Path(self.tmp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(self.remote)], check=True, capture_output=True)
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Test'); self.git('config', 'user.email', 'test@example.invalid')
        (self.root / '.gitignore').write_text('.publisher-local/\ndist/\n')
        self.catalog = PhotoCatalog(self.root)
        atomic_json(self.catalog.path, [])
        self.git('add', '.'); self.git('commit', '-m', 'initial')
        self.git('remote', 'add', 'origin', str(self.remote)); self.git('push', '-u', 'origin', 'main')

    def tearDown(self): self.tmp.cleanup()
    def git(self, *args): return publishing.git(self.root, *args)
    def review(self):
        atomic_json(self.catalog.local / 'review.json', {'fingerprint': publishing.fingerprint(self.catalog),
          'head': self.git('rev-parse', 'HEAD'), 'branch': 'main'})

    def test_only_reviewed_photo_files_are_committed_and_pushed(self):
        atomic_json(self.catalog.path, [{'id': 'legacy', 'date': '2026-09-23', 'title': '作品'}])
        self.review()
        result = publishing.publish(self.catalog)
        self.assertIn('commit', result)
        self.assertEqual(self.git('show', '--pretty=', '--name-only', 'HEAD'), 'src/data/photos.json')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.git('rev-parse', 'origin/main'))

    def test_new_changes_invalidate_preview_and_originals_are_blocked(self):
        self.review()
        atomic_json(self.catalog.path, [{'id': 'changed'}])
        with self.assertRaisesRegex(ValueError, '重新生成'):
            publishing.publish(self.catalog)
        self.review()
        (self.root / 'original.jpg').write_bytes(b'original')
        with self.assertRaisesRegex(ValueError, '照片以外'):
            publishing.publish(self.catalog)

    def test_unrelated_local_commits_are_never_pushed(self):
        (self.root / 'other.txt').write_text('unrelated')
        self.git('add', 'other.txt'); self.git('commit', '-m', 'unrelated')
        self.review()
        with self.assertRaisesRegex(ValueError, '未同步提交'):
            publishing.publish(self.catalog)

    def test_failed_push_can_be_retried_without_duplicate_commit(self):
        atomic_json(self.catalog.path, [{'id': 'new', 'title': '作品'}])
        self.review()
        original = publishing.git
        def failing(root, *args):
            if args[0] == 'push': raise ValueError('network')
            return original(root, *args)
        with patch.object(publishing, 'git', side_effect=failing):
            with self.assertRaisesRegex(ValueError, 'network'): publishing.publish(self.catalog)
        commit = self.git('rev-parse', 'HEAD')
        publishing.publish(self.catalog)
        self.assertEqual(commit, self.git('rev-parse', 'HEAD'))
        self.assertEqual(commit, self.git('rev-parse', 'origin/main'))

    def test_preview_server_serves_build_and_can_stop(self):
        output = self.root / 'dist/photos'
        output.mkdir(parents=True)
        (output / 'index.html').write_text('preview works')
        package_root = str(Path(__file__).resolve().parents[1])
        original_popen = subprocess.Popen
        children = []
        def tracked_popen(args, *extra, **kwargs):
            child = original_popen(args, *extra, **kwargs)
            if len(args) > 1 and str(args[1]).endswith('preview_server.py'):
                children.append(child)
            return child
        with patch.dict(os.environ, {'PYTHONPATH': package_root}), patch.object(publishing, 'build'), patch.object(subprocess, 'Popen', side_effect=tracked_popen):
            try:
                result = publishing.preview(self.catalog)
                with urllib.request.urlopen(result['url'], timeout=5) as response:
                    self.assertEqual(response.read(), b'preview works')
            finally:
                (self.catalog.local / 'preview-session').unlink(missing_ok=True)
                for child in children:
                    child.wait(timeout=5)


if __name__ == '__main__': unittest.main()
