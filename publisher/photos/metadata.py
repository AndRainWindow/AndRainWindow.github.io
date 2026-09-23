"""Read camera metadata before conversion; do not invent missing capture times."""
from __future__ import annotations

import base64
import io
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps


def text(value) -> str:
    if isinstance(value, bytes):
        value = value.decode('utf-8', errors='replace')
    return str(value or '').strip().strip('\x00')


def number(value) -> str:
    try:
        return f'{float(value):g}'
    except (ValueError, TypeError, ZeroDivisionError):
        return ''


def capture_date(value) -> str:
    try:
        return datetime.strptime(text(value), '%Y:%m:%d %H:%M:%S').isoformat(timespec='minutes')
    except ValueError:
        return ''


def coordinates(gps) -> dict | None:
    try:
        def decimal(values, ref):
            d, m, s = [float(v) for v in values]
            return (d + m / 60 + s / 3600) * (-1 if text(ref) in ('S', 'W') else 1)
        lat, lon = decimal(gps[2], gps[1]), decimal(gps[4], gps[3])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return {'lat': lat, 'lon': lon}
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    return None


def inspect_photo(source: str) -> dict:
    path = Path(source).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
        raise ValueError(f'请选择 JPG/JPEG、PNG 或 WebP 文件：{path.name}')
    with Image.open(path) as img:
        img.verify()
    with Image.open(path) as img:
        exif = img.getexif()
        details = exif.get_ifd(0x8769)
        gps = coordinates(exif.get_ifd(0x8825))
        exposure = details.get(33434)
        shutter = number(exposure)
        try:
            if 0 < float(exposure) < 1:
                shutter = f'1/{round(1 / float(exposure))}'
        except (TypeError, ValueError, ZeroDivisionError):
            pass
        camera = text(exif.get(272))
        make = text(exif.get(271))
        if make and not camera.lower().startswith(make.lower()):
            camera = f'{make} {camera}'.strip()
        return {
            'source': str(path), 'filename': path.name,
            'title': '', 'note': '', 'location': '',
            'date': capture_date(details.get(36867)),
            'camera': camera, 'lens': text(details.get(42036)),
            'iso': number(details.get(34855)),
            'aperture': number(details.get(33437)),
            'shutter': shutter, 'focalLength': number(details.get(37386)),
            'utcOffset': text(details.get(36881)),
            'gps': gps,
        }


def thumbnail(path: Path, box: tuple[int, int] = (640, 480)) -> str:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail(box)
        buffer = io.BytesIO()
        img.convert('RGB').save(buffer, 'JPEG', quality=80)
        return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')
