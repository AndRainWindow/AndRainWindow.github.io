import json
import subprocess
import tempfile
import os
import urllib.request
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageCms
from publisher.photos.catalog import PhotoCatalog, atomic_json, project_lock
from publisher.photos.metadata import inspect_photo
from publisher.photos.service import dispatch
from publisher.photos import publish as publishing
from publisher.photos import geocode


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
