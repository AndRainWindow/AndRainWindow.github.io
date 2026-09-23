from pathlib import Path

from .catalog import PhotoCatalog, project_lock
from .metadata import inspect_photo


def dispatch(root: Path, payload: dict) -> dict:
    catalog = PhotoCatalog(root)
    with project_lock(catalog.root):
        action = payload.get('action')
        if action == 'list':
            return catalog.listing()
        if action == 'inspect':
            paths = payload.get('paths', [])
            if not paths or len(paths) > 200:
                raise ValueError('每次请选择 1–200 张照片。')
            items, errors = [], []
            for source in paths:
                try:
                    item = inspect_photo(source)
                    if item.get('gps'):
                        from .geocode import preferences, lookup
                        if preferences(catalog, {}).get('configured'):
                            try:
                                located = lookup(catalog, {'source': source})
                                item.update({key: located[key] for key in ('location', 'locationSource')})
                            except ValueError as exc:
                                errors.append(f'{Path(source).name}: {exc}')
                    items.append(item)
                except Exception as exc:
                    errors.append(f'{Path(source).name}: {exc}')
            return {'selection': items, 'errors': errors}
        if action == 'thumbnail':
            return catalog.thumbnail(payload)
        if action == 'import':
            return catalog.import_group(payload)
        if action == 'update':
            return catalog.update(payload['id'], payload['changes'])
        if action == 'update-group':
            return catalog.update_group(payload['id'], payload['changes'])
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
