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
    if changes.get('locationSource') == 'geoapify':
        result['locationSource'] = 'geoapify'
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

    def import_group(self, payload: dict) -> dict:
        items = payload.get('photos', [])
        if not items or len(items) > 200:
            raise ValueError('每次请选择 1–200 张照片。')
        group_title = str(payload.get('title', '')).strip()
        group_note = str(payload.get('note', '')).strip()
        if not group_title:
            raise ValueError('请填写整组标题。')
        data = self.load()
        known = {p.get('sourceHash') for p in data}
        private = read_json(self.local / 'sources.json', {})
        group_id = uuid.uuid4().hex
        imported, skipped, prepared = [], [], []
        # Validate the whole selection before writing. Missing dates must be supplied by the user.
        for item in items:
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
            for source, digest, original, values in prepared:
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
            # Private data is never published or copied into catalogue records.
            atomic_json(self.local / 'sources.json', private)
            atomic_json(self.path, data + imported)
        except Exception:
            for target in created:
                target.unlink(missing_ok=True)
            raise
        return {**self.listing(), 'message': f'已保存 {len(imported)} 张，跳过重复照片 {len(skipped)} 张。请先本地预览。'}

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

    def update_group(self, group_id: str, changes: dict) -> dict:
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
