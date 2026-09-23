from pathlib import Path

from .catalog import PhotoCatalog, project_lock
from .metadata import inspect_photo, thumbnail


def dispatch(root: Path, payload: dict, on_event=None) -> dict:
    catalog = PhotoCatalog(root)
    with project_lock(catalog.root):
        action = payload.get('action')
        if action == 'list':
            return catalog.listing()
        if action == 'inspect':
            paths = payload.get('paths', [])
            if not paths or len(paths) > 200:
                raise ValueError('每次请选择 1–200 张照片。')
            # Location is resolved during import, not here: a batch of GPS-tagged
            # photos would otherwise block this request on per-photo lookups.
            items, errors = [], []
            for source in paths:
                try:
                    item = inspect_photo(source)
                    item['thumb'] = thumbnail(Path(item['source']), box=(320, 240))
                    items.append(item)
                except Exception as exc:
                    errors.append(f'{Path(source).name}: {exc}')
            return {'selection': items, 'errors': errors}
        if action == 'thumbnail':
            return catalog.thumbnail(payload)
        if action == 'import':
            return catalog.import_group(payload, on_event)
        if action == 'update':
            return catalog.update(payload['id'], payload['changes'])
        if action == 'update-group':
            return catalog.update_group(payload['id'], payload['changes'],
                                        order=payload.get('order'), cover=payload.get('cover'),
                                        note_to_all=bool(payload.get('noteToAll')))
        if action in ('geo-preferences', 'geocode'):
            from .geocode import preferences, lookup
            return (preferences if action == 'geo-preferences' else lookup)(catalog, payload)
        if action in ('preview', 'publish'):
            from .publish import preview, publish
            return (preview if action == 'preview' else publish)(catalog)
        if action == 'stop-preview':
            (catalog.local / 'preview-session').unlink(missing_ok=True)
            return {'message': '本地预览已停止。'}
        raise ValueError('不支持的照片操作。')
