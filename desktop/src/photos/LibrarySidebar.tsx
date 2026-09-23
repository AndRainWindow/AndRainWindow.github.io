// 左侧照片库：组→照片 两级导航。组行可展开，子行为单张缩略图 + 时间 + 标题。
import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { libraryImageSrc } from './groups';
import type { PhotoGroup, Selection } from './types';

function hhmm(date: string): string {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(date) ? date.slice(11, 16) : '';
}

function ChildThumb({ image, alt }: { image?: string; alt: string }) {
  const [failed, setFailed] = useState(false);
  const src = libraryImageSrc(image);
  if (!src || failed) {
    return <span className="photo-child-thumb photo-child-thumb-missing" aria-hidden="true" />;
  }
  return <img className="photo-child-thumb" src={src} alt={alt} loading="lazy" onError={() => setFailed(true)} />;
}

interface Props {
  groups: PhotoGroup[];
  selection: Selection | null;
  blocked: boolean;
  trash: boolean;
  onSelect: (selection: Selection) => void;
}

export default function LibrarySidebar({ groups, selection, blocked, trash, onSelect }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  if (groups.length === 0) {
    return <div className="photo-list"><p>{trash ? '回收站是空的。' : '当前没有照片。'}</p></div>;
  }

  return <div className="photo-list">
    {groups.map(group => {
      const isOpen = expanded.has(group.id);
      const groupSelected = selection?.type === 'group' && selection.groupId === group.id;
      const displayTitle = group.title || group.cover.title || '未命名组';
      return <div key={group.id} className="photo-group-row">
        <div className="photo-group-head">
          <button className="photo-group-toggle" disabled={blocked} aria-expanded={isOpen}
            aria-label={isOpen ? `收起 ${displayTitle}` : `展开 ${displayTitle}`}
            onClick={() => toggle(group.id)}>
            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
          <button className={`photo-list-select ${groupSelected ? 'selected' : ''}`} disabled={blocked}
            onClick={() => onSelect({ type: 'group', groupId: group.id })}>
            <strong>{displayTitle}</strong>
            <small>{(group.date || '').replace('T', ' ')} · {group.photos.length} 张{group.hidden ? ' · 已隐藏' : ''}{group.deleted ? ' · 回收站' : ''}</small>
          </button>
          <button className="text-button" disabled={blocked}
            onClick={() => onSelect({ type: 'group', groupId: group.id })}>整组</button>
        </div>
        {isOpen && <div className="photo-child-list">
          {group.photos.map(photo => {
            const selected = selection?.type === 'photo' && selection.photoId === photo.id;
            const badge = [(photo.hidden || group.hidden) ? '已隐藏' : '',
              (photo.deleted || group.deleted) ? '回收站' : ''].filter(Boolean).join(' · ');
            return <button key={photo.id} className={`photo-child-row ${selected ? 'selected' : ''}`} disabled={blocked}
              onClick={() => photo.id && onSelect({ type: 'photo', groupId: group.id, photoId: photo.id })}>
              <ChildThumb image={photo.image} alt={photo.title || group.title || '照片'} />
              <span className="photo-child-meta">
                <strong>{photo.title || group.title || '未命名照片'}</strong>
                <small>{[hhmm(photo.date) || (photo.date || '').slice(0, 10), photo.title ? '' : '单张', badge]
                  .filter(Boolean).join(' · ')}</small>
              </span>
            </button>;
          })}
        </div>}
      </div>;
    })}
  </div>;
}
