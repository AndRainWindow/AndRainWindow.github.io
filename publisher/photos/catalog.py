"""Atomic photo catalogue edits. Original files and GPS stay on the local machine."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from PIL import Image

from ..processors.webp import WebPProcessor
from .metadata import inspect_photo, thumbnail

FIELDS = ('title', 'note', 'date', 'location', 'camera', 'lens', 'iso', 'aperture',
          'shutter', 'focalLength', 'utcOffset')
FLAGS = ('hidden', 'deleted')


def read_json(path: Path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def project_lock(root: Path):
    """OS-owned lock is automatically released even after a crashed process."""
    local = root / '.publisher-local'
    local.mkdir(exist_ok=True)
    with (local / 'photos.lock').open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('已有照片任务正在运行，请稍后重试。') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def validate_date(value: str):
    if len(value) not in (10, 16):
        raise ValueError('请填写拍摄日期，格式为 YYYY-MM-DD 或 YYYY-MM-DDTHH:mm。')
    datetime.strptime(value, '%Y-%m-%d' if len(value) == 10 else '%Y-%m-%dT%H:%M')


def edits(changes: dict) -> dict:
    result = {key: str(changes[key]).strip() for key in FIELDS if key in changes}
    if 'date' in result:
        validate_date(result['date'])
    for key in FLAGS:
        if key in changes:
            if not isinstance(changes[key], bool):
                raise ValueError('照片状态必须为布尔值。')
            result[key] = changes[key]
    if changes.get('locationSource') in ('geoapify', 'amap'):
        result['locationSource'] = changes['locationSource']
    return result


class PhotoCatalog:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.path = self.root / 'src/data/photos.json'
        self.local = self.root / '.publisher-local'
        self.output = self.root / 'public/images/photos'

    def load(self) -> list[dict]:
        data = read_json(self.path, [])
        if not isinstance(data, list) or any(not isinstance(row, dict) or not row.get('id') for row in data):
            raise ValueError('photos.json 格式错误，未修改任何照片。')
        if len({p['id'] for p in data}) != len(data):
            raise ValueError('photos.json 中有重复 ID，请先修复。')
        return data

    def listing(self) -> dict:
        private = read_json(self.local / 'sources.json', {})
        return {'photos': [{**p, 'hasGps': bool(private.get(p['id'], {}).get('gps'))} for p in self.load()]}

    def sweep_orphans(self) -> None:
        """Delete generated WebP files no row references (e.g. a killed import).

        Only the generated `photo-<32 hex>.webp` naming pattern is eligible, so
        manually placed files are never touched. Without this, an orphan wedges
        preview/publish: it is dirty in git but outside the publish whitelist.
        """
        if not self.output.is_dir():
            return
        referenced = {Path(row['image']).name for row in self.load() if row.get('image')}
        for path in self.output.iterdir():
            name = path.name
            if not path.is_file() or name in referenced:
                continue
            stem = name[len('photo-'):-len('.webp')]
            if (name.startswith('photo-') and name.endswith('.webp') and len(stem) == 32
                    and all(c in '0123456789abcdef' for c in stem)):
                path.unlink(missing_ok=True)

    def import_group(self, payload: dict, on_event=None) -> dict:
        def emit(phase: str, current: int, total: int, filename: str = '') -> None:
            if on_event:
                on_event({'phase': phase, 'current': current, 'total': total,
                          'filename': filename, 'taskId': payload.get('taskId', '')})

        items = payload.get('photos', [])
        if not items or len(items) > 200:
            raise ValueError('每次请选择 1–200 张照片。')
        group_title = str(payload.get('title', '')).strip()
        group_note = str(payload.get('note', '')).strip()
        if not group_title and len(items) > 1:
            raise ValueError('多张照片请填写整组标题；单张导入可留空。')
        self.sweep_orphans()
        data = self.load()
        known = {p.get('sourceHash') for p in data}
        private = read_json(self.local / 'sources.json', {})
        group_id = uuid.uuid4().hex
        imported, skipped, prepared, errors = [], [], [], []
        # Validate the whole selection before writing. Missing dates must be supplied by the user.
        for index, item in enumerate(items):
            emit('inspect', index + 1, len(items), Path(item.get('source', '')).name)
            original = inspect_photo(item['source'])
            values = edits({**{key: item.get(key, original.get(key, '')) for key in FIELDS},
                            'locationSource': item.get('locationSource')})
            source = Path(original['source'])
            with source.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest in known:
                skipped.append(original['filename'])
                continue
            known.add(digest)
            prepared.append((source, digest, original, values))
        self.output.mkdir(parents=True, exist_ok=True)
        created = []
        try:
            for index, (source, digest, original, values) in enumerate(prepared):
                emit('convert', index + 1, len(prepared), source.name)
                photo_id = f'photo-{uuid.uuid4().hex}'
                target = self.output / f'{photo_id}.webp'
                with tempfile.TemporaryDirectory() as tmp:
                    result = WebPProcessor().convert(source, tmp, preset='photo')
                    converted = Path(result['output'])
                    if not result['converted'] or not converted.is_file() or converted.suffix != '.webp':
                        raise ValueError(f'WebP 转换失败：{source.name}，未发布原图。')
                    with Image.open(converted) as check:
                        if check.format != 'WEBP':
                            raise ValueError('转换输出不是 WebP。')
                        check.verify()
                    # Same filesystem for atomic final rename.
                    fd, stage = tempfile.mkstemp(dir=self.output, suffix='.tmp')
                    os.close(fd)
                    try:
                        Path(stage).write_bytes(converted.read_bytes())
                        os.replace(stage, target)
                    finally:
                        Path(stage).unlink(missing_ok=True)
                created.append(target)
                row = {**values, 'id': photo_id, 'image': f'/images/photos/{target.name}',
                       'groupId': group_id, 'groupTitle': group_title, 'groupNote': group_note,
                       'sourceHash': digest, 'hidden': False, 'deleted': False}
                imported.append(row)
                private[photo_id] = {'source': str(source), 'gps': original['gps']}
            errors.extend(self._locate_batch(imported, private, emit))
            # Import order = capture time ascending; cover is photos[0] on the site.
            if len(imported) > 1:
                for order, row in enumerate(sorted(imported, key=lambda row: row['date'] or '9999-99-99')):
                    row['order'] = order
            # Private data is never published or copied into catalogue records.
            atomic_json(self.local / 'sources.json', private)
            atomic_json(self.path, data + imported)
        except Exception:
            for target in created:
                target.unlink(missing_ok=True)
            raise
        emit('finalize', 1, 1)
        message = f'已保存 {len(imported)} 张，跳过重复照片 {len(skipped)} 张。请先本地预览。'
        if errors:
            message += f'（{len(errors)} 处地点识别失败，可稍后逐张重试。）'
        return {**self.listing(), 'message': message, 'errors': errors}

    def _locate_batch(self, rows: list[dict], private: dict, emit) -> list[str]:
        """Reverse-geocode each distinct coordinate once; failures never abort the import."""
        coords: dict[str, list[dict]] = {}
        for row in rows:
            gps = private.get(row['id'], {}).get('gps')
            if gps:
                coords.setdefault(f"{gps['lat']:.5f},{gps['lon']:.5f}", []).append(row)
        if not coords:
            return []
        from .geocode import preferences
        if not preferences(self, {}).get('configured'):
            return []
        from .geocode import lookup
        errors = []
        for index, (key, members) in enumerate(coords.items()):
            lat, lon = key.split(',')
            emit('geocode', index + 1, len(coords), f'{len(members)} 张照片')
            try:
                located = lookup(self, {'lat': float(lat), 'lon': float(lon)})
            except ValueError as exc:
                errors.append(f'{key}: {exc}')
                continue
            for row in members:
                row.update({field: located[field] for field in
                            ('location', 'locationSource', 'province', 'city', 'district')
                            if located.get(field)})
        return errors

    def update(self, photo_id: str, changes: dict) -> dict:
        data = self.load()
        row = next((p for p in data if p['id'] == photo_id), None)
        if row is None:
            raise ValueError('照片不存在，请刷新列表。')
        row.update(edits(changes))
        # A manually entered location supersedes the geocoded location.
        if 'location' in changes and changes.get('locationSource') != 'geoapify':
            row.pop('locationSource', None)
        atomic_json(self.path, data)
        return self.listing()

    def update_group(self, group_id: str, changes: dict, order=None, cover=None,
                     note_to_all: bool = False) -> dict:
        data = self.load()
        members = [p for p in data if p.get('groupId', p['id']) == group_id]
        if not members:
            raise ValueError('照片组不存在。')
        for row in members:
            for key in ('groupTitle', 'groupNote'):
                if key in changes:
                    row[key] = str(changes[key]).strip()
            for key in ('groupHidden', 'groupDeleted'):
                if key in changes:
                    if not isinstance(changes[key], bool):
                        raise ValueError('组状态必须为布尔值。')
                    row[key] = changes[key]
        if note_to_all and 'groupNote' in changes:
            # Explicit one-click action: the group note becomes every photo's own note.
            note = str(changes['groupNote']).strip()
            for row in members:
                row['note'] = note
        ids = {p['id'] for p in members}
        if order is not None:
            if (not isinstance(order, list) or len(order) != len(members)
                    or {str(photo_id) for photo_id in order} != ids):
                raise ValueError('照片顺序与组成员不一致，请刷新后重试。')
            for index, photo_id in enumerate(order):
                next(p for p in members if p['id'] == str(photo_id))['order'] = index
        if cover is not None:
            if cover not in ids:
                raise ValueError('封面照片不在本组内。')
            head = next(p for p in members if p['id'] == cover)
            tail = sorted((p for p in members if p['id'] != cover),
                          key=lambda p: (p.get('order', 1 << 30), p['date']))
            for index, row in enumerate([head, *tail]):
                row['order'] = index
        atomic_json(self.path, data)
        return self.listing()

    def thumbnail(self, payload: dict) -> dict:
        if payload.get('source'):
            path = Path(inspect_photo(payload['source'])['source'])
        else:
            row = next((p for p in self.load() if p['id'] == payload.get('id')), None)
            if not row:
                raise ValueError('照片不存在。')
            path = (self.root / 'public' / row['image'].lstrip('/')).resolve()
            if not path.is_relative_to((self.root / 'public').resolve()):
                raise ValueError('照片路径超出网站目录。')
        return {'thumbnail': thumbnail(path)}
