// 整组编辑器：组标题/感受（含一键写入每张）、组日期（=封面拍摄日期）、封面选择、成员排序。
// 标题/感受是本地草稿（切换组时重置）；封面/排序是结构性操作，直接调父级保存。
import { useRef, useState } from 'react';
import { libraryImageSrc } from './groups';
import type { PhotoGroup } from './types';

function CoverThumb({ image, alt }: { image?: string; alt: string }) {
  const [failed, setFailed] = useState(false);
  const src = libraryImageSrc(image);
  if (!src || failed) {
    return <span className="photo-child-thumb photo-child-thumb-missing" aria-hidden="true" />;
  }
  return <img className="photo-child-thumb" src={src} alt={alt} loading="lazy" onError={() => setFailed(true)} />;
}

interface Props {
  group: PhotoGroup;
  blocked: boolean;
  onDirty: () => void;
  onSaveFields: (title: string, note: string) => void;
  onNoteToAll: (title: string, note: string) => void;
  onCoverDate: (date: string) => void;
  onCover: (photoId: string) => void;
  onReorder: (orderIds: string[]) => void;
  onToggleGroupHidden: () => void;
  onToggleGroupDeleted: () => void;
}

export default function GroupEditor({ group, blocked, onDirty, onSaveFields, onNoteToAll,
  onCoverDate, onCover, onReorder, onToggleGroupHidden, onToggleGroupDeleted }: Props) {
  const [title, setTitle] = useState(group.title);
  const [note, setNote] = useState(group.note);
  const [orderIds, setOrderIds] = useState<string[]>(() => group.photos.map(p => p.id!));
  const identity = `${group.id}:${group.cover.id}:${group.photos.length}`;
  const lastIdentity = useRef(identity);
  if (lastIdentity.current !== identity) {
    lastIdentity.current = identity;
    setOrderIds(group.photos.map(p => p.id!));
  }

  const move = (index: number, direction: -1 | 1) => {
    setOrderIds(prev => {
      const next = [...prev];
      const target = index + direction;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    onDirty();
  };
  const byId = new Map(group.photos.map(p => [p.id!, p]));
  const reordered = orderIds.map(id => byId.get(id)!).filter(Boolean);
  const orderChanged = orderIds.join('|') !== group.photos.map(p => p.id).join('|');
  const coverDate = (group.cover.date || '').slice(0, 10);
  const coverHasTime = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(group.cover.date || '');

  return <>
    <h3>整组信息 · {group.photos.length} 张</h3>
    <p>组标题和感受只在组内第一张可见照片展示；单张填写的标题和感受优先。</p>
    <label className="photo-wide-label">组标题<input value={title} disabled={blocked}
      onChange={e => { setTitle(e.target.value); onDirty(); }} /></label>
    <label className="photo-wide-label">组感受<textarea value={note} disabled={blocked} rows={6}
      onChange={e => { setNote(e.target.value); onDirty(); }} /></label>
    <div className="action-row">
      <button className="button primary" disabled={blocked} onClick={() => onSaveFields(title, note)}>
        保存整组修改</button>
      <button className="button ghost" disabled={blocked || !note.trim()}
        onClick={() => onNoteToAll(title, note)}>将组感受写入整组</button>
      <small>写入后每张照片的感受仍可单独修改。</small>
    </div>
    <div className="photo-fields">
      <label>组日期（即封面照片的拍摄日期）
        <input type="date" value={coverDate} disabled={blocked}
          onChange={e => onCoverDate(coverHasTime && e.target.value ? `${e.target.value}T${(group.cover.date || '').slice(11, 16)}` : e.target.value)} />
        <small>改动会保存到封面照片上，组在时间线中的位置随之变化。</small>
      </label>
    </div>
    <p className="photo-exif-caption">封面（点击缩略图更换）</p>
    <div className="photo-thumb-strip">
      {group.photos.map(photo => <div key={photo.id}
        className={`photo-thumb-item ${photo.id === group.cover.id ? 'cover' : ''}`}>
        <button className="photo-thumb-pick" disabled={blocked} onClick={() => onCover(photo.id!)}>
          <CoverThumb image={photo.image} alt={photo.title || group.title || '照片'} />
          <small>{photo.id === group.cover.id ? '当前封面' : '设为封面'}</small>
        </button>
      </div>)}
    </div>
    <p className="photo-exif-caption">组内顺序（公开页按此顺序展示）</p>
    <div className="photo-order-list">
      {reordered.map((photo, index) => <div key={photo.id} className="photo-order-row">
        <span className="photo-order-index">{index + 1}</span>
        <span className="photo-order-name">{photo.title || group.title || '未命名照片'}
          <small>{(photo.date || '').replace('T', ' ')}</small></span>
        <span className="photo-thumb-tools">
          <button className="text-button" disabled={blocked || index === 0}
            aria-label={`前移 ${photo.title || index + 1}`} onClick={() => move(index, -1)}>↑</button>
          <button className="text-button" disabled={blocked || index === reordered.length - 1}
            aria-label={`后移 ${photo.title || index + 1}`} onClick={() => move(index, 1)}>↓</button>
        </span>
      </div>)}
    </div>
    <div className="action-row">
      <button className="button secondary" disabled={blocked || !orderChanged}
        onClick={() => onReorder(orderIds)}>保存排序</button>
    </div>
    <div className="action-row">
      <button className="button secondary" disabled={blocked} onClick={onToggleGroupHidden}>
        {group.hidden ? '取消整组隐藏' : '隐藏整组'}</button>
      <button className="button secondary" disabled={blocked}
        onClick={() => { if (group.deleted || window.confirm('将整组照片移入回收站？组内照片仍可恢复。')) onToggleGroupDeleted(); }}>
        {group.deleted ? '恢复整组' : '整组移入回收站'}</button>
    </div>
  </>;
}
