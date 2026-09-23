"""Optional Geoapify lookup; only city/county-level text reaches public metadata."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from .catalog import atomic_json, read_json


def preferences(catalog, payload):
    path = catalog.local / 'geocoding.json'
    current = read_json(path, {})
    if 'apiKey' in payload:
        current['apiKey'] = str(payload['apiKey']).strip()
        atomic_json(path, current)
    return {'configured': bool(current.get('apiKey'))}


def lookup(catalog, payload):
    from .metadata import inspect_photo
    if payload.get('source'):
        gps = inspect_photo(payload['source'])['gps']
    else:
        gps = read_json(catalog.local / 'sources.json', {}).get(payload.get('id'), {}).get('gps')
    if not gps:
        raise ValueError('这张照片没有可用的 GPS 信息，请手动填写地点。')
    prefs = read_json(catalog.local / 'geocoding.json', {})
    key = prefs.get('apiKey', '')
    if not key:
        raise ValueError('请先在摄影页配置 Geoapify API Key，或手动填写地点。')
    cache_path = catalog.local / 'geocode-cache.json'
    cache = read_json(cache_path, {})
    cache_key = f"{gps['lat']:.5f},{gps['lon']:.5f}"
    if cache_key in cache:
        return cache[cache_key]
    params = urllib.parse.urlencode({**gps, 'format': 'json', 'lang': 'zh', 'apiKey': key})
    # Persisted throttle applies across separate CLI invocations.
    throttle = catalog.local / 'geocode-last.json'
    last = read_json(throttle, {'time': 0})['time']
    time.sleep(max(0, 1.1 - (time.time() - last)))
    atomic_json(throttle, {'time': time.time()})
    request = urllib.request.Request(
        'https://api.geoapify.com/v1/geocode/reverse?' + params,
        headers={'User-Agent': 'AndRainWindowPublisher/0.2.0'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            results = json.load(response).get('results', [])
    except Exception as exc:
        # Avoid leaking the API key from an HTTP error URL into logs.
        raise ValueError('地点查询失败，请检查网络及 API Key，或手动填写地点。') from None
    if not results:
        raise ValueError('地图服务没有返回地点，请手动填写。')
    result = results[0]
    city = result.get('city') or result.get('state') or ''
    district = result.get('district') or result.get('county') or ''
    location = ' · '.join(dict.fromkeys(p for p in (city, district) if p))
    if not location:
        raise ValueError('地图服务未提供城市／区县信息，请手动填写。')
    value = {'location': location, 'locationSource': 'geoapify',
             'message': '已识别到区县，请核对。' if district else '仅识别到城市，请补充区县。'}
    cache[cache_key] = value
    atomic_json(cache_path, cache)
    return value
