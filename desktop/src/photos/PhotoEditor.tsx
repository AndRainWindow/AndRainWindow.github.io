// 单张照片编辑器。pending 模式直接改父级的待导入项；saved 模式先落本地草稿再保存。
// 拍摄日期拆成 日期+时间 两个输入：legacy 日期（仅 YYYY-MM-DD）也能正常显示和编辑。
import { useRef, useState } from 'react';
import type { PhotoRow } from './types';

const EQUIP_FIELDS: [keyof PhotoRow, string][] = [
  ['camera', '相机'], ['lens', '镜头'],
];
const EXPOSURE_FIELDS: [keyof PhotoRow, string][] = [
  ['focalLength', '焦距 (mm)'], ['aperture', '光圈 f/'],
  ['shutter', '快门'], ['iso', 'ISO'],
];

function splitDate(date: string): [string, string] {
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(date)) return [date.slice(0, 10), date.slice(11, 16)];
  if (/^\d{4}-\d{2}-\d{2}$/.test(date)) return [date, ''];
  return ['', ''];
}

function composeDate(datePart: string, timePart: string): string {
  return timePart && datePart ? `${datePart}T${timePart}` : datePart;
}

interface Props {
  photo: PhotoRow;
  mode: 'pending' | 'saved';
  blocked: boolean;
  previewSrc: string | null;
  geoReady: boolean;
  busyText?: string;
  onChange?: (patch: Partial<PhotoRow>) => void;
  onDirty?: () => void;
  onSave?: (draft: PhotoRow) => void;
  onGeocode?: () => void;
  onSetSharedLocation?: () => void;
  onToggleHidden?: () => void;
  onToggleDeleted?: () => void;
}

export default function PhotoEditor({ photo, mode, blocked, previewSrc, geoReady,
  busyText, onChange, onDirty, onSave, onGeocode, onSetSharedLocation,
  onToggleHidden, onToggleDeleted }: Props) {
  // saved 模式的本地草稿：选择切换（id/source 变化）时重置。
  const [draft, setDraft] = useState<PhotoRow>(photo);
  const identity = photo.id ?? photo.source ?? '';
  const lastIdentity = useRef(identity);
  if (lastIdentity.current !== identity) {
    lastIdentity.current = identity;
    setDraft(photo);
  }
  const value = mode === 'pending' ? photo : draft;

  const patch = (changes: Partial<PhotoRow>) => {
    if (mode === 'pending') {
      onChange?.(changes);
    } else {
      setDraft(prev => ({ ...prev, ...changes }));
      onDirty?.();
    }
  };
  const setField = (key: keyof PhotoRow, fieldValue: string) => {
    patch({ [key]: fieldValue, ...(key === 'location' ? { locationSource: undefined } : {}) } as Partial<PhotoRow>);
  };

  const [datePart, timePart] = splitDate(value.date || '');
  const hasGps = Boolean(value.gps || value.hasGps);

  return <>
    <h3>{mode === 'pending' ? '导入前检查' : '单张照片'}</h3>
    {previewSrc && <img className="photo-thumbnail" src={previewSrc} alt="选中照片预览" />}
    <div className="photo-fields">
      <label>单张标题（留空沿用组规则）<input value={value.title || ''} disabled={blocked}
        onChange={e => setField('title', e.target.value)} /></label>
      <label>拍摄日期与时间
        <span className="photo-datetime">
          <input type="date" aria-label="拍摄日期" value={datePart} disabled={blocked}
            onChange={e => setField('date', composeDate(e.target.value, timePart))} />
          <input type="time" aria-label="拍摄时间" value={timePart} disabled={blocked}
            onChange={e => setField('date', composeDate(datePart, e.target.value))} />
        </span>
        <small>{value.utcOffset ? `时区 ${value.utcOffset}；左侧仅显示 HH:mm` : '左侧仅显示 HH:mm；时间可留空'}</small>
      </label>
      <label>地点（城市 · 区县，可手动修正）<input value={value.location || ''} disabled={blocked}
        onChange={e => setField('location', e.target.value)} /></label>
    </div>
    <p className="photo-exif-caption">设备</p>
    <div className="photo-fields">
      {EQUIP_FIELDS.map(([field, label]) => <label key={field}>{label}
        <input value={String(value[field] || '')} disabled={blocked}
          onChange={e => setField(field, e.target.value)} /></label>)}
    </div>
    <p className="photo-exif-caption">曝光</p>
    <div className="photo-fields">
      {EXPOSURE_FIELDS.map(([field, label]) => <label key={field}>{label}
        <input value={String(value[field] || '')} disabled={blocked}
          onChange={e => setField(field, e.target.value)} /></label>)}
    </div>
    <label className="photo-wide-label">单张感受（留空沿用组规则）<textarea value={value.note || ''}
      disabled={blocked} rows={4} onChange={e => setField('note', e.target.value)} /></label>
    <div className="action-row">
      <span className="photo-gps-state">{hasGps ? '已记录 GPS 坐标（仅保存在本机）' : '无 GPS，地点可手动填写'}</span>
      <button className="button secondary" disabled={blocked || !hasGps || !geoReady}
        onClick={() => onGeocode?.()}>GPS 识别区县</button>
      {mode === 'pending' && onSetSharedLocation && value.location &&
        <button className="button ghost" disabled={blocked} onClick={onSetSharedLocation}>设为本组默认地点</button>}
      {mode === 'saved' && onSave &&
        <button className="button primary" disabled={blocked} onClick={() => onSave(draft)}>
          保存单张修改</button>}
    </div>
    {mode === 'saved' && (onToggleHidden || onToggleDeleted) && <div className="action-row">
      {onToggleHidden && <button className="button secondary" disabled={blocked} onClick={onToggleHidden}>
        {photo.hidden ? '取消单张隐藏' : '隐藏单张'}</button>}
      {onToggleDeleted && <button className="button secondary" disabled={blocked} onClick={onToggleDeleted}>
        {(photo.deleted) ? '恢复单张' : '移入回收站'}</button>}
      {(photo.groupHidden || photo.groupDeleted) &&
        <small>所属组已隐藏／删除，请在“整组”中恢复后才会展示。</small>}
    </div>}
    {busyText && <small>{busyText}</small>}
  </>;
}
