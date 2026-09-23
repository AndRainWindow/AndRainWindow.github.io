"""Optional reverse geocoding (Geoapify or AMap); only city/district text reaches public metadata."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from .catalog import atomic_json, read_json
from .coord import wgs84_to_gcj02

PROVIDERS = ('geoapify', 'amap')


def preferences(catalog, payload):
    path = catalog.local / 'geocoding.json'
    current = read_json(path, {})
    changed = False
    if 'apiKey' in payload:
        current['apiKey'] = str(payload['apiKey']).strip()
        changed = True
    if 'amapKey' in payload:
        current['amapKey'] = str(payload['amapKey']).strip()
        changed = True
    if payload.get('provider') in PROVIDERS:
        current['provider'] = payload['provider']
        changed = True
    if changed:
        atomic_json(path, current)
    provider = current.get('provider', 'geoapify')
    return {'configured': bool(current.get('apiKey' if provider == 'geoapify' else 'amapKey')),
            'provider': provider,
            'geoapify': bool(current.get('apiKey')),
            'amap': bool(current.get('amapKey'))}


def lookup(catalog, payload):
    from .metadata import inspect_photo
    if payload.get('source'):
        gps = inspect_photo(payload['source'])['gps']
    else:
        gps = read_json(catalog.local / 'sources.json', {}).get(payload.get('id'), {}).get('gps')
    if not gps and payload.get('lat') is not None and payload.get('lon') is not None:
        gps = {'lat': float(payload['lat']), 'lon': float(payload['lon'])}
    if not gps:
        raise ValueError('这张照片没有可用的 GPS 信息，请手动填写地点。')
    prefs = read_json(catalog.local / 'geocoding.json', {})
    provider = prefs.get('provider', 'geoapify')
    key = prefs.get('apiKey' if provider == 'geoapify' else 'amapKey', '')
    if not key:
        name = 'Geoapify' if provider == 'geoapify' else '高德'
        raise ValueError(f'请先在摄影页配置{name} API Key，或手动填写地点。')
    cache_path = catalog.local / 'geocode-cache.json'
    cache = read_json(cache_path, {})
    cache_key = f"{provider}:{gps['lat']:.5f},{gps['lon']:.5f}"
    # Cache entries written before providers existed are Geoapify results.
    legacy_key = f"{gps['lat']:.5f},{gps['lon']:.5f}"
    if cache_key in cache or (provider == 'geoapify' and legacy_key in cache):
        return cache.get(cache_key) or cache[legacy_key]
    if provider == 'geoapify':
        value = _lookup_geoapify(catalog, gps, key)
    else:
        value = _lookup_amap(catalog, gps, key)
    cache[cache_key] = value
    atomic_json(cache_path, cache)
    return value


def _throttle(catalog, filename: str, interval: float) -> None:
    # Persisted throttle applies across separate CLI invocations.
    throttle = catalog.local / filename
    last = read_json(throttle, {'time': 0})['time']
    time.sleep(max(0, interval - (time.time() - last)))
    atomic_json(throttle, {'time': time.time()})


def _compose(province: str, city: str, district: str, provider: str) -> dict:
    # Municipalities return an empty city; the province then reads better alone.
    city = city or province
    location = ' · '.join(dict.fromkeys(p for p in (city, district) if p))
    if not location:
        raise ValueError('地图服务未提供城市／区县信息，请手动填写。')
    return {'location': location, 'locationSource': provider,
            'province': province, 'city': city, 'district': district,
            'message': '已识别到区县，请核对。' if district else '仅识别到城市，请补充区县。'}


def _lookup_geoapify(catalog, gps, key):
    params = urllib.parse.urlencode({**gps, 'format': 'json', 'lang': 'zh', 'apiKey': key})
    _throttle(catalog, 'geocode-last.json', 1.1)
    request = urllib.request.Request(
        'https://api.geoapify.com/v1/geocode/reverse?' + params,
        headers={'User-Agent': 'AndRainWindowPublisher/0.2.0'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            results = json.load(response).get('results', [])
    except Exception as exc:
        # Avoid leaking the API key from an HTTP error URL into logs.
        raise ValueError('Geoapify 地点查询失败，请检查网络及 API Key，或手动填写地点。') from None
    if not results:
        raise ValueError('地图服务没有返回地点，请手动填写。')
    result = results[0]
    province = result.get('state') or ''
    return _compose(province, result.get('city') or '',
                    result.get('district') or result.get('county') or '', 'geoapify')


def _lookup_amap(catalog, gps, key):
    lat, lon = wgs84_to_gcj02(gps['lat'], gps['lon'])
    params = urllib.parse.urlencode({'key': key, 'location': f'{lon:.6f},{lat:.6f}'})
    _throttle(catalog, 'geocode-last-amap.json', 0.2)
    request = urllib.request.Request(
        'https://restapi.amap.com/v3/geocode/regeo?' + params,
        headers={'User-Agent': 'AndRainWindowPublisher/0.2.0'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.load(response)
    except Exception as exc:
        raise ValueError('高德地点查询失败，请检查网络及 Key，或手动填写地点。') from None
    if str(body.get('status')) != '1':
        info = body.get('info') or '未知错误'
        if 'INVALID_USER_KEY' in str(info):
            raise ValueError('高德 Key 无效或未开通 Web 服务，请检查后重试。')
        raise ValueError(f'高德地点查询失败：{info}，请手动填写地点。')
    component = (body.get('regeocode') or {}).get('addressComponent') or {}

    def part(value):
        return value if isinstance(value, str) else ''

    return _compose(part(component.get('province')), part(component.get('city')),
                    part(component.get('district')), 'amap')
