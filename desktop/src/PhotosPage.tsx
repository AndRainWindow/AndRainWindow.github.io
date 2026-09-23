import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import { Camera, Eye, FolderOpen, LoaderCircle, RefreshCw, Save, Send } from 'lucide-react';

interface Photo {
  id?: string; source?: string; filename?: string; image?: string;
  title: string; note: string; date: string; location: string; camera: string;
  lens?: string; iso?: string; aperture?: string; shutter?: string; focalLength?: string;
  groupId?: string; groupTitle?: string; groupNote?: string;
  hidden?: boolean; deleted?: boolean; groupHidden?: boolean; groupDeleted?: boolean;
  gps?: { lat: number; lon: number } | null; hasGps?: boolean; locationSource?: string;
}
interface Result {
  photos?: Photo[]; selection?: Photo[]; errors?: string[];
  thumbnail?: string; location?: string; locationSource?: string;
  url?: string; message?: string; configured?: boolean;
}
interface Props {
  active: boolean; project: string; disabled: boolean;
  onBusy: (busy: boolean) => void; onLog: (message: string) => void;
}
const empty: Photo = { title: '', note: '', date: '', location: '', camera: '' };
const metadataFields: [keyof Photo, string][] = [
  ['camera', '相机'], ['lens', '镜头'], ['iso', 'ISO'], ['aperture', '光圈 f/'],
  ['shutter', '快门（秒）'], ['focalLength', '焦距（mm）'],
];

export default function PhotosPage({ active, project, disabled, onBusy, onLog }: Props) {
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [selection, setSelection] = useState<Photo[]>([]);
  const [selected, setSelected] = useState(-1);
  const [editing, setEditing] = useState<Photo | null>(null);
  const [group, setGroup] = useState<Photo | null>(null);
  const [groupTitle, setGroupTitle] = useState('');
  const [groupNote, setGroupNote] = useState('');
  const [fallbackDate, setFallbackDate] = useState('');
  const [sharedLocation, setSharedLocation] = useState('');
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [thumbnail, setThumbnail] = useState('');
  const [message, setMessage] = useState('先选择一组 JPG 照片，或管理已经导入的作品。');
  const [isError, setError] = useState(false);
  const [working, setWorking] = useState(false);
  const [previewUrl, setPreviewUrl] = useState('');
  const [geoKey, setGeoKey] = useState('');
  const [geoConfigured, setGeoConfigured] = useState(false);
  const [dirty, setDirty] = useState(false);
  const loadedProject = useRef('');
  const inFlight = useRef(false);
  const blocked = disabled || working;
  const current = selected >= 0 ? selection[selected] : editing;

  async function request(payload: Record<string, unknown>, status: string): Promise<Result | null> {
    if (inFlight.current || disabled) return null;
    inFlight.current = true;
    setWorking(true); onBusy(true); setError(false); setMessage(status);
    try {
      const result = await invoke<Result>('photo_request', { payload });
      if (result.photos) setPhotos(result.photos);
      if (result.configured !== undefined) setGeoConfigured(result.configured);
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
    setSelection([]); setSelected(-1); setEditing(null); setGroup(null); setPreviewUrl(''); setDirty(false);
    void (async () => {
      const result = await request({ action: 'list' }, '正在读取照片库…');
      if (!result) { loadedProject.current = ''; return; }
      await request({ action: 'geo-preferences' }, '正在检查地点识别设置…');
    })();
  }, [active, project, disabled]);

  function canSwitch() {
    return !dirty || window.confirm('单张／组信息尚未保存，放弃这些修改？');
  }

  async function showPhoto(photo: Photo, index = -1) {
    if (!canSwitch()) return;
    setSelected(index); setEditing(index < 0 ? { ...empty, ...photo } : null); setGroup(null);
    setDirty(false); setThumbnail('');
    const result = await request({ action: 'thumbnail', ...(photo.source ? { source: photo.source } : { id: photo.id }) }, '正在载入照片…');
    if (result?.thumbnail) setThumbnail(result.thumbnail);
  }

  async function chooseFiles() {
    if (!canSwitch()) return;
    try {
      const paths = await open({ multiple: true, directory: false,
        filters: [{ name: '照片', extensions: ['jpg', 'jpeg', 'JPG', 'JPEG', 'png', 'webp'] }] });
      if (!paths) return;
      const result = await request({ action: 'inspect', paths: Array.isArray(paths) ? paths : [paths] }, '正在读取拍摄参数…');
      if (!result?.selection) return;
      setSelection(result.selection); setSelected(-1); setEditing(null); setGroup(null); setDirty(false);
      setThumbnail(''); setPreviewUrl('');
      setMessage(`已选 ${result.selection.length} 张。${(result.errors || []).join('；')}`);
    } catch (error) { setMessage(String(error)); setError(true); }
  }

  function changePhoto(key: keyof Photo, value: string) {
    if (selected >= 0) {
      setSelection(prev => prev.map((p, i) => i === selected ? { ...p, [key]: value, ...(key === 'location' ? { locationSource: undefined } : {}) } : p));
    } else {
      setEditing(prev => prev ? { ...prev, [key]: value, ...(key === 'location' ? { locationSource: undefined } : {}) } : prev); setDirty(true);
    }
    setPreviewUrl('');
  }

  async function importSelection() {
    const result = await request({ action: 'import', title: groupTitle, note: groupNote,
      photos: selection.map(photo => ({ ...photo, date: photo.date || fallbackDate,
        location: photo.location || sharedLocation })) }, '正在转换 WebP 并保存整组照片，原图保留在本地…');
    if (result) {
      setSelection([]); setSelected(-1); setEditing(null); setThumbnail('');
      setGroupTitle(''); setGroupNote(''); setPreviewUrl(''); setDirty(false);
    }
  }

  async function updatePhoto(changes: Partial<Photo>) {
    if (!editing?.id) return;
    const result = await request({ action: 'update', id: editing.id, changes: { ...editing, ...changes } }, '正在保存照片信息…');
    if (result) {
      setEditing(result.photos?.find(p => p.id === editing.id) || null);
      setPreviewUrl(''); setDirty(false);
    }
  }

  async function updateGroup(changes: Partial<Photo>) {
    if (!group) return;
    const id = group.groupId || group.id;
    const result = await request({ action: 'update-group', id, changes: { groupTitle: group.groupTitle || '', groupNote: group.groupNote || '', ...changes } }, '正在保存整组信息…');
    if (result) {
      setGroup(result.photos?.find(p => (p.groupId || p.id) === id) || null);
      setPreviewUrl(''); setDirty(false);
    }
  }

  async function geocode() {
    if (!current) return;
    const result = await request({ action: 'geocode', ...(current.source ? { source: current.source } : { id: current.id }) }, '正在识别城市和区县…');
    if (result?.location) {
      if (selected >= 0) setSelection(prev => prev.map((p, i) => i === selected ? { ...p, location: result.location!, locationSource: result.locationSource } : p));
      else { setEditing(prev => prev ? { ...prev, location: result.location!, locationSource: result.locationSource } : prev); setDirty(true); }
      setPreviewUrl('');
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

  const displayed = photos.filter(p => {
    const deleted = p.deleted || p.groupDeleted;
    const hidden = p.hidden || p.groupHidden;
    return (filter === 'trash' ? deleted : !deleted && (filter !== 'hidden' || hidden)) &&
      `${p.title} ${p.groupTitle || ''} ${p.location} ${p.date}`.toLowerCase().includes(search.toLowerCase());
  }).sort((a, b) => b.date.localeCompare(a.date));

  return <div className="page">
    <header className="page-header"><h1>摄影管理</h1><p>整组导入、单张编辑。保存到本地，预览满意后再上线。</p></header>
    <div className="page-body">
      <div className={`photo-status ${isError ? 'error' : ''}`} role="status" aria-live="polite">
        {working && <LoaderCircle size={18} className="spin" />}<span>{message}</span>
      </div>
      <section className="panel photo-publish-bar">
        <button className="button primary" disabled={blocked} onClick={() => void chooseFiles()}><FolderOpen size={16}/>选择一组照片</button>
        <button className="button secondary" disabled={blocked || dirty || selection.length > 0} onClick={() => void preview()}><Eye size={16}/>生成本地预览</button>
        <button className="button primary" disabled={blocked || !previewUrl || dirty || selection.length > 0} onClick={async () => {
          if (!window.confirm('确认已检查本地预览？将仅提交照片信息和 WebP，并推送到网站。')) return;
          const result = await request({ action: 'publish' }, '正在提交并推送照片修改…');
          if (result) setPreviewUrl('');
        }}><Send size={16}/>确认并提交上线</button>
        {previewUrl && <span className="photo-preview-url">{previewUrl}</span>}
      </section>

      {selection.length > 0 && <section className="panel photo-import">
        <h3>新照片组 · {selection.length} 张</h3>
        <div className="photo-fields">
          <label>整组标题<input value={groupTitle} disabled={blocked} onChange={e => setGroupTitle(e.target.value)}/></label>
          <label>缺失拍摄日期时补填<input type="date" value={fallbackDate} disabled={blocked} onChange={e => setFallbackDate(e.target.value)}/></label>
          <label>整组默认地点（城市 · 区县）<input value={sharedLocation} disabled={blocked} onChange={e => setSharedLocation(e.target.value)}/></label>
        </div>
        <label className="photo-wide-label">整组感受<textarea value={groupNote} disabled={blocked} onChange={e => setGroupNote(e.target.value)} rows={3}/></label>
        <p>整组标题和感受仅在第一张可见照片上显示。下方可选中单张，填写独立标题、感受或修正拍摄时间。</p>
        <div className="photo-selection">{selection.map((photo, i) => <button key={`${photo.source}-${i}`} className={`button ${selected === i ? 'primary' : 'secondary'}`} disabled={blocked} onClick={() => void showPhoto(photo, i)}>{photo.filename}{!photo.date ? ' · 缺少日期' : ''}</button>)}</div>
        <div className="action-row">
          <button className="button primary" disabled={blocked || !groupTitle.trim()} onClick={() => void importSelection()}><Save size={16}/>保存整组到本地</button>
          <button className="button ghost" disabled={blocked} onClick={() => { setSelection([]); setSelected(-1); setThumbnail(''); }}>取消本次导入</button>
        </div>
      </section>}

      <div className="photo-manager-grid">
        <section className="panel photo-library">
          <div className="panel-toolbar"><h3>照片库 · {photos.length}</h3><button className="button ghost" disabled={blocked} onClick={() => void request({ action: 'list' }, '正在刷新照片库…')}><RefreshCw size={15}/></button></div>
          <div className="photo-filter"><input aria-label="搜索照片" placeholder="搜索标题、地点、日期" value={search} onChange={e => setSearch(e.target.value)}/><select aria-label="筛选状态" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">全部照片</option><option value="hidden">已隐藏</option><option value="trash">回收站</option></select></div>
          <div className="photo-list">{displayed.map(photo => <div className="photo-list-row" key={photo.id}>
            <button className={`photo-list-select ${editing?.id === photo.id ? 'selected' : ''}`} disabled={blocked} onClick={() => void showPhoto(photo)}><strong>{photo.title || photo.groupTitle || '未命名照片'}</strong><small>{photo.date.replace('T', ' ')}{(photo.hidden || photo.groupHidden) ? ' · 已隐藏' : ''}{(photo.deleted || photo.groupDeleted) ? ' · 回收站' : ''}</small></button>
            <button className="text-button" disabled={blocked} onClick={() => { if (!canSwitch()) return; setGroup({ ...photo }); setEditing(null); setSelected(-1); setDirty(false); setThumbnail(''); }}>整组</button>
          </div>)}{displayed.length === 0 && <p>当前没有照片。</p>}</div>
        </section>

        <section className="panel photo-editor">
          {current ? <>
            <h3>{selected >= 0 ? '导入前检查' : '单张照片'}</h3>
            {thumbnail && <img className="photo-thumbnail" src={thumbnail} alt="选中照片预览"/>}
            <div className="photo-fields">
              <label>单张标题（留空沿用组规则）<input value={current.title} disabled={blocked} onChange={e => changePhoto('title', e.target.value)}/></label>
              <label>拍摄日期与时间<input type="datetime-local" step="60" value={current.date.length > 10 ? current.date.slice(0, 16) : ''} disabled={blocked} onChange={e => changePhoto('date', e.target.value)}/><small>{current.date.length === 10 ? `仅有日期：${current.date}，不会显示 00:00` : '右侧仅显示 HH:mm；左侧保留年月日'}</small></label>
              <label>地点（城市 · 区县）<input value={current.location} disabled={blocked} onChange={e => changePhoto('location', e.target.value)}/></label>
              {metadataFields.map(([field, label]) => <label key={field}>{label}<input value={String(current[field] || '')} disabled={blocked} onChange={e => changePhoto(field, e.target.value)}/></label>)}
            </div>
            <label className="photo-wide-label">单张感受（留空沿用组规则）<textarea value={current.note} disabled={blocked} rows={4} onChange={e => changePhoto('note', e.target.value)}/></label>
            <div className="action-row">
              <button className="button secondary" disabled={blocked || !(current.gps || current.hasGps) || !geoConfigured} onClick={() => void geocode()}>GPS 识别区县</button>
              {selected >= 0 && current.location && <button className="button ghost" disabled={blocked} onClick={() => setSharedLocation(current.location)}>设为本组默认地点</button>}
              {editing && <button className="button primary" disabled={blocked} onClick={() => void updatePhoto(editing)}><Save size={16}/>保存单张修改</button>}
            </div>
            {editing && <div className="action-row">
              <button className="button secondary" disabled={blocked} onClick={() => void updatePhoto({ hidden: !editing.hidden })}>{editing.hidden ? '取消单张隐藏' : '隐藏单张'}</button>
              <button className="button secondary" disabled={blocked} onClick={() => { if (editing.deleted || window.confirm('将此照片移入回收站？可恢复，不删除本地原图。')) void updatePhoto({ deleted: !editing.deleted }); }}>{editing.deleted ? '恢复单张' : '移入回收站'}</button>
              {(editing.groupHidden || editing.groupDeleted) && <small>所属组已隐藏／删除，请在“整组”中恢复后才会展示。</small>}
            </div>}
          </> : group ? <>
            <h3>整组信息</h3>
            <label className="photo-wide-label">组标题<input value={group.groupTitle || ''} disabled={blocked} onChange={e => { setGroup({ ...group, groupTitle: e.target.value }); setDirty(true); }}/></label>
            <label className="photo-wide-label">组感受<textarea value={group.groupNote || ''} disabled={blocked} rows={6} onChange={e => { setGroup({ ...group, groupNote: e.target.value }); setDirty(true); }}/></label>
            <p>只在组内第一张可见照片展示；单张填写的标题和感受优先。</p>
            <div className="action-row">
              <button className="button primary" disabled={blocked} onClick={() => void updateGroup({ groupTitle: group.groupTitle || '', groupNote: group.groupNote || '' })}>保存整组修改</button>
              <button className="button secondary" disabled={blocked} onClick={() => void updateGroup({ groupHidden: !group.groupHidden })}>{group.groupHidden ? '取消整组隐藏' : '隐藏整组'}</button>
              <button className="button secondary" disabled={blocked} onClick={() => { if (group.groupDeleted || window.confirm('将整组照片移入回收站？组内照片仍可恢复。')) void updateGroup({ groupDeleted: !group.groupDeleted }); }}>{group.groupDeleted ? '恢复整组' : '整组移入回收站'}</button>
            </div>
          </> : <div className="photo-empty"><Camera size={36}/><p>选择一张照片查看预览和拍摄信息。</p></div>}
        </section>
      </div>

      <details className="panel photo-geocoding"><summary>GPS 地点识别 · {geoConfigured ? '已配置' : '可选配置'}</summary>
        <p>读取 GPS 在本地完成。查询区县时，仅向 Geoapify 发送坐标；不上传 JPG。原始坐标和密钥仅保存在本机。</p>
        <div className="photo-fields"><label>Geoapify API Key<input type="password" autoComplete="off" value={geoKey} disabled={blocked} onChange={e => setGeoKey(e.target.value)} placeholder="仅保存到本地"/></label></div>
        <button className="button secondary" disabled={blocked || !geoKey.trim()} onClick={async () => { const r = await request({ action: 'geo-preferences', apiKey: geoKey }, '正在保存地点识别设置…'); if (r) setGeoKey(''); }}>保存密钥</button>
        <p>服务与地点数据：Geoapify / OpenStreetMap。识别结果可手动校正；没有 GPS 的照片直接填写地点即可。</p>
        <small>照片“隐藏”仅控制网页展示。公开仓库里的 WebP 仍可能通过直接链接访问。</small>
      </details>
    </div>
  </div>;
}
