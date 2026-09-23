// 摄影管理主页面：编排层。库（组→照片两级）、本次导入、单张/整组编辑、地理编码设置。
// 后端操作仍经 photo_request 单飞互斥；导入进度通过 publisher://photo-event 流式更新，
// 事件不来（如测试桩）也必须能正常完成导入。
import { useEffect, useMemo, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { open } from '@tauri-apps/plugin-dialog';
import { Camera, Eye, FolderOpen, LoaderCircle, RefreshCw, Send } from 'lucide-react';
import GroupEditor from './photos/GroupEditor';
import ImportStage from './photos/ImportStage';
import LibrarySidebar from './photos/LibrarySidebar';
import PhotoEditor from './photos/PhotoEditor';
import { libraryCounts, libraryImageSrc, sortForImport, toGroups } from './photos/groups';
import type { BridgeResult, GeoState, PendingPhoto, PhotoEvent, PhotoRow, Selection } from './photos/types';

const empty: PhotoRow = { title: '', note: '', date: '', location: '' };

interface Props {
  active: boolean; project: string; disabled: boolean;
  onBusy: (busy: boolean) => void; onLog: (message: string) => void;
}

export default function PhotosPage({ active, project, disabled, onBusy, onLog }: Props) {
  const [rows, setRows] = useState<PhotoRow[]>([]);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [pending, setPending] = useState<PendingPhoto[]>([]);
  const [pendingSource, setPendingSource] = useState<string | null>(null);
  const [groupTitle, setGroupTitle] = useState('');
  const [groupNote, setGroupNote] = useState('');
  const [fallbackDate, setFallbackDate] = useState('');
  const [sharedLocation, setSharedLocation] = useState('');
  const [importProgress, setImportProgress] = useState<PhotoEvent | null>(null);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [geo, setGeo] = useState<GeoState>({ configured: false, provider: 'geoapify', geoapify: false, amap: false });
  const [geoKey, setGeoKey] = useState('');
  const [amapKey, setAmapKey] = useState('');
  const [message, setMessage] = useState('先选择一组 JPG 照片，或管理已经导入的作品。');
  const [isError, setError] = useState(false);
  const [working, setWorking] = useState(false);
  const [previewUrl, setPreviewUrl] = useState('');
  const [dirty, setDirty] = useState(false);
  const loadedProject = useRef('');
  const inFlight = useRef(false);
  const importTaskId = useRef('');
  const blocked = disabled || working;

  const groups = useMemo(() => toGroups(rows), [rows]);
  const counts = useMemo(() => libraryCounts(rows), [rows]);
  const countsLabel = filter === 'trash'
    ? `回收站 · ${countsLabelOf(rows, true)} 张`
    : `照片库 · ${counts.groups} 组 · ${counts.photos} 张`;

  const selectedGroup = useMemo(() => {
    if (selection?.type !== 'group') return null;
    return groups.find(g => g.id === selection.groupId) ?? null;
  }, [groups, selection]);
  const selectedPhoto = useMemo(() => {
    if (selection?.type !== 'photo') return null;
    const group = groups.find(g => g.id === selection.groupId);
    return group?.photos.find(p => p.id === selection.photoId) ?? null;
  }, [groups, selection]);
  const selectedPending = useMemo(
    () => pending.find(p => p.source === pendingSource) ?? null, [pending, pendingSource]);

  async function request(payload: Record<string, unknown>, status: string): Promise<BridgeResult | null> {
    if (inFlight.current || disabled) return null;
    inFlight.current = true;
    setWorking(true); onBusy(true); setError(false); setMessage(status);
    try {
      const result = await invoke<BridgeResult>('photo_request', { payload });
      if (result.photos) setRows(result.photos);
      if (result.configured !== undefined) {
        setGeo(prev => ({
          configured: result.configured ?? prev.configured,
          provider: result.provider ?? prev.provider,
          geoapify: result.geoapify ?? prev.geoapify,
          amap: result.amap ?? prev.amap,
        }));
      }
      const text = result.message || '操作完成。';
      setMessage(text); onLog(text);
      return result;
    } catch (error) {
      setError(true); setMessage(String(error)); onLog(`[ERROR] ${String(error)}`);
      return null;
    } finally {
      inFlight.current = false; setWorking(false); onBusy(false);
    }
  }

  useEffect(() => {
    if (!active || disabled || !project || loadedProject.current === project) return;
    loadedProject.current = project;
    setSelection(null); setPending([]); setPendingSource(null); setPreviewUrl(''); setDirty(false);
    void (async () => {
      const result = await request({ action: 'list' }, '正在读取照片库…');
      if (!result) { loadedProject.current = ''; return; }
      await request({ action: 'geo-preferences' }, '正在检查地点识别设置…');
    })();
  }, [active, project, disabled]);

  // 导入进度事件：按 taskId 过滤，避免陈旧任务串扰；没有事件也照常完成。
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let cancelled = false;
    void listen<PhotoEvent>('publisher://photo-event', event => {
      const detail = event.payload;
      if (detail?.taskId && detail.taskId === importTaskId.current) setImportProgress(detail);
    }).then(fn => { if (cancelled) fn(); else unlisten = fn; });
    return () => { cancelled = true; unlisten?.(); };
  }, []);

  function canSwitch() {
    return !dirty || window.confirm('单张／组信息尚未保存，放弃这些修改？');
  }

  // 纯同步选择切换：预览地址由 groups.ts 现算，不再异步取缩略图（消除旧竞态）。
  function select(next: Selection) {
    if (!canSwitch()) return;
    setSelection(next);
    setDirty(false);
  }

  function selectPending(source: string) {
    if (!canSwitch()) return;
    setPendingSource(source);
    setDirty(false);
  }

  async function chooseFiles() {
    if (!canSwitch()) return;
    try {
      const paths = await open({ multiple: true, directory: false,
        filters: [{ name: '照片', extensions: ['jpg', 'jpeg', 'JPG', 'JPEG', 'png', 'webp'] }] });
      if (!paths) return;
      const result = await request({ action: 'inspect', paths: Array.isArray(paths) ? paths : [paths] }, '正在读取拍摄参数…');
      if (!result?.selection) return;
      const ordered = sortForImport(result.selection);
      setPending(ordered); setPendingSource(ordered[0]?.source ?? null);
      setSelection(null); setDirty(false); setPreviewUrl('');
      setMessage(`已选 ${ordered.length} 张。${(result.errors || []).join('；')}`);
    } catch (error) { setMessage(String(error)); setError(true); }
  }

  function patchPending(source: string, changes: Partial<PendingPhoto>) {
    setPending(prev => prev.map(p => p.source === source ? { ...p, ...changes } : p));
  }

  function movePending(source: string, direction: -1 | 1) {
    setPending(prev => {
      const index = prev.findIndex(p => p.source === source);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function coverPending(source: string) {
    setPending(prev => {
      const item = prev.find(p => p.source === source);
      if (!item) return prev;
      return [item, ...prev.filter(p => p.source !== source)];
    });
  }

  function noteToAllPending() {
    setPending(prev => prev.map(p => ({ ...p, note: groupNote })));
    setMessage('已把整组感受写入每张照片，可再逐张修改。');
  }

  async function importSelection() {
    importTaskId.current = crypto.randomUUID();
    setImportProgress(null);
    const photos = pending.map(({ thumb, gps, hasGps, ...rest }) =>
      ({ ...rest, date: rest.date || fallbackDate, location: rest.location || sharedLocation }));
    const result = await request({ action: 'import', taskId: importTaskId.current,
      title: groupTitle, note: groupNote, photos },
      '正在转换 WebP 并保存整组照片，原图保留在本地…');
    setImportProgress(null);
    if (result) {
      setPending([]); setPendingSource(null); setGroupTitle(''); setGroupNote('');
      setFallbackDate(''); setSharedLocation(''); setPreviewUrl(''); setDirty(false);
    }
  }

  async function updatePhoto(photo: PhotoRow, changes: Partial<PhotoRow>): Promise<BridgeResult | null> {
    // 完整行合并提交：update 只接受白名单字段，缺的会被当作空串覆盖。
    const result = await request({ action: 'update', id: photo.id,
      changes: { ...empty, ...photo, ...changes } }, '正在保存照片信息…');
    if (result) setDirty(false);
    return result;
  }

  async function updateGroup(groupId: string, changes: Partial<PhotoRow>,
    extra: { order?: string[]; cover?: string; noteToAll?: boolean } = {}) {
    const current = groups.find(g => g.id === groupId);
    const result = await request({ action: 'update-group', id: groupId,
      changes: { groupTitle: current?.title ?? '', groupNote: current?.note ?? '', ...changes },
      ...extra }, '正在保存整组信息…');
    if (result) setDirty(false);
    return result;
  }

  async function geocodeCurrent() {
    const target = selectedPending ?? selectedPhoto;
    if (!target) return;
    const result = await request({ action: 'geocode', ...(target.source ? { source: target.source } : { id: target.id }) },
      '正在识别城市和区县…');
    if (result?.location) {
      const located = { location: result.location, locationSource: result.locationSource };
      if (selectedPending) {
        patchPending(selectedPending.source, located);
      } else if (selectedPhoto) {
        await updatePhoto(selectedPhoto, located);
      }
    }
  }

  async function preview() {
    const result = await request({ action: 'preview' }, '正在构建本地预览…');
    if (result?.url) {
      setPreviewUrl(result.url);
      try { await invoke('open_preview', { url: result.url }); }
      catch { setMessage(`预览已生成，请在浏览器打开：${result.url}`); }
    }
  }

  const displayedRows = useMemo(() => rows.filter(p => {
    const deleted = p.deleted || p.groupDeleted;
    const hidden = p.hidden || p.groupHidden;
    return (filter === 'trash' ? deleted : !deleted && (filter !== 'hidden' || hidden)) &&
      `${p.title} ${p.groupTitle || ''} ${p.location} ${p.date}`.toLowerCase().includes(search.toLowerCase());
  }), [rows, filter, search]);
  const displayedGroups = useMemo(() => toGroups(displayedRows), [displayedRows]);

  const pendingPreview = selectedPending?.thumb ?? null;
  const savedPreview = selectedPhoto ? libraryImageSrc(selectedPhoto.image) : null;

  return <div className="page">
    <header className="page-header"><h1>摄影管理</h1><p>整组导入、单张编辑。保存到本地，预览满意后再上线。</p></header>
    <div className="page-body">
      <div className={`photo-status ${isError ? 'error' : ''}`} role="status" aria-live="polite">
        {working && <LoaderCircle size={18} className="spin" />}<span>{message}</span>
      </div>
      <section className="panel photo-publish-bar">
        <button className="button primary" disabled={blocked} onClick={() => void chooseFiles()}><FolderOpen size={16}/>选择一组照片</button>
        <button className="button secondary" disabled={blocked || dirty || pending.length > 0} onClick={() => void preview()}><Eye size={16}/>生成本地预览</button>
        <button className="button primary" disabled={blocked || !previewUrl || dirty || pending.length > 0} onClick={async () => {
          if (!window.confirm('确认已检查本地预览？将仅提交照片信息和 WebP，并推送到网站。')) return;
          const result = await request({ action: 'publish' }, '正在提交并推送照片修改…');
          if (result) setPreviewUrl('');
        }}><Send size={16}/>确认并提交上线</button>
        {previewUrl && <span className="photo-preview-url">{previewUrl}</span>}
      </section>

      {pending.length > 0 && <ImportStage
        pending={pending} selectedSource={pendingSource} blocked={blocked}
        progress={importProgress}
        groupTitle={groupTitle} onGroupTitle={setGroupTitle}
        groupNote={groupNote} onGroupNote={setGroupNote}
        fallbackDate={fallbackDate} onFallbackDate={setFallbackDate}
        sharedLocation={sharedLocation} onSharedLocation={setSharedLocation}
        onNoteToAll={noteToAllPending}
        onSelect={selectPending} onMove={movePending} onCover={coverPending}
        onImport={() => void importSelection()}
        onCancel={() => { setPending([]); setPendingSource(null); setImportProgress(null); }} />}

      <div className="photo-manager-grid">
        <section className="panel photo-library">
          <div className="panel-toolbar"><h3>{countsLabel}</h3>
            <button className="button ghost" disabled={blocked} onClick={() => void request({ action: 'list' }, '正在刷新照片库…')}>
              <RefreshCw size={15}/></button></div>
          <div className="photo-filter"><input aria-label="搜索照片" placeholder="搜索标题、地点、日期" value={search}
            onChange={e => setSearch(e.target.value)} />
            <select aria-label="筛选状态" value={filter} onChange={e => setFilter(e.target.value)}>
              <option value="all">全部照片</option><option value="hidden">已隐藏</option><option value="trash">回收站</option>
            </select></div>
          <LibrarySidebar groups={displayedGroups} selection={selection} blocked={blocked}
            trash={filter === 'trash'} onSelect={select} />
        </section>

        <section className="panel photo-editor">
          {selectedPending ? <PhotoEditor key={selectedPending.source} photo={selectedPending} mode="pending"
            blocked={blocked} previewSrc={pendingPreview} geoReady={geo.configured}
            onChange={patch => patchPending(selectedPending.source, patch)}
            onGeocode={() => void geocodeCurrent()}
            onSetSharedLocation={() => setSharedLocation(selectedPending.location)} />
            : selectedPhoto ? <PhotoEditor key={selectedPhoto.id} photo={selectedPhoto} mode="saved"
              blocked={blocked} previewSrc={savedPreview} geoReady={geo.configured}
              onDirty={() => setDirty(true)}
              onSave={draft => { if (selectedPhoto.id) void updatePhoto(selectedPhoto, draft); }}
              onGeocode={() => void geocodeCurrent()}
              onToggleHidden={() => void updatePhoto(selectedPhoto, { hidden: !selectedPhoto.hidden })}
              onToggleDeleted={() => {
                if (selectedPhoto.deleted || window.confirm('将此照片移入回收站？可恢复，不删除本地原图。')) {
                  void updatePhoto(selectedPhoto, { deleted: !selectedPhoto.deleted });
                }
              }} />
              : selectedGroup ? <GroupEditor key={selectedGroup.id} group={selectedGroup} blocked={blocked}
                onDirty={() => setDirty(true)}
                onSaveFields={(title, note) => void updateGroup(selectedGroup.id, { groupTitle: title, groupNote: note })}
                onNoteToAll={(title, note) => void updateGroup(selectedGroup.id,
                  { groupTitle: title, groupNote: note }, { noteToAll: true })}
                onCoverDate={date => void updatePhoto(selectedGroup.cover, { date })}
                onCover={photoId => void updateGroup(selectedGroup.id, {}, { cover: photoId })}
                onReorder={orderIds => void updateGroup(selectedGroup.id, {}, { order: orderIds })}
                onToggleGroupHidden={() => void updateGroup(selectedGroup.id, { groupHidden: !selectedGroup.hidden })}
                onToggleGroupDeleted={() => {
                  if (selectedGroup.deleted || window.confirm('将整组照片移入回收站？组内照片仍可恢复。')) {
                    void updateGroup(selectedGroup.id, { groupDeleted: !selectedGroup.deleted });
                  }
                }} />
                : <div className="photo-empty"><Camera size={36} /><p>选择一个组或一张照片查看和编辑。</p></div>}
        </section>
      </div>

      <details className="panel photo-geocoding">
        <summary>GPS 地点识别 · {geo.configured ? `已配置（${geo.provider === 'amap' ? '高德' : 'Geoapify'}）` : '可选配置'}</summary>
        <p>读取 GPS 在本地完成。查询区县时仅向所选服务发送坐标；不上传 JPG。原始坐标和密钥仅保存在本机。
          高德会自动把 WGS84 坐标转换为 GCJ02（仅限中国大陆）。</p>
        <div className="photo-fields">
          <label>服务<select value={geo.provider} disabled={blocked}
            onChange={e => void request({ action: 'geo-preferences', provider: e.target.value }, '正在保存地点识别设置…')}>
            <option value="geoapify">Geoapify（国际）</option>
            <option value="amap">高德 AMap（国内）</option>
          </select></label>
          <label>Geoapify API Key<input type="password" autoComplete="off" value={geoKey} disabled={blocked}
            onChange={e => setGeoKey(e.target.value)} placeholder="仅保存到本地" /></label>
          <label>高德 Web 服务 Key<input type="password" autoComplete="off" value={amapKey} disabled={blocked}
            onChange={e => setAmapKey(e.target.value)} placeholder="仅保存到本地" /></label>
        </div>
        <div className="action-row">
          <button className="button secondary" disabled={blocked || !geoKey.trim()}
            onClick={async () => { const r = await request({ action: 'geo-preferences', apiKey: geoKey }, '正在保存地点识别设置…'); if (r) setGeoKey(''); }}>
            保存 Geoapify Key</button>
          <button className="button secondary" disabled={blocked || !amapKey.trim()}
            onClick={async () => { const r = await request({ action: 'geo-preferences', amapKey, provider: 'amap' }, '正在保存地点识别设置…'); if (r) setAmapKey(''); }}>
            保存高德 Key</button>
        </div>
        <p>服务与地点数据：Geoapify / OpenStreetMap，或高德地图。识别结果可手动校正；没有 GPS 的照片直接填写地点即可。</p>
        <small>照片“隐藏”仅控制网页展示。公开仓库里的 WebP 仍可能通过直接链接访问。</small>
      </details>
    </div>
  </div>;
}

function countsLabelOf(rows: PhotoRow[], trash: boolean): number {
  return rows.filter(p => trash ? (p.deleted || p.groupDeleted) : !(p.deleted || p.groupDeleted)).length;
}
