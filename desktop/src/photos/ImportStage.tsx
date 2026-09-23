// “本次导入”区：数量、缩略图条（inspect 自带，零额外请求）、排序/封面、组信息、进度。
// n=1 时是简单的单张编辑体验（不出现组字段）；n≥2 才按小系列/批量处理。
import { PHASE_LABELS } from './types';
import type { PendingPhoto, PhotoEvent } from './types';

interface Props {
  pending: PendingPhoto[];
  selectedSource: string | null;
  blocked: boolean;
  progress: PhotoEvent | null;
  groupTitle: string; onGroupTitle: (value: string) => void;
  groupNote: string; onGroupNote: (value: string) => void;
  fallbackDate: string; onFallbackDate: (value: string) => void;
  sharedLocation: string; onSharedLocation: (value: string) => void;
  onNoteToAll: () => void;
  onSelect: (source: string) => void;
  onMove: (source: string, direction: -1 | 1) => void;
  onCover: (source: string) => void;
  onImport: () => void;
  onCancel: () => void;
}

function Progress({ progress }: { progress: PhotoEvent }) {
  const percent = progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;
  return <div className="photo-progress" role="status">
    <span>{PHASE_LABELS[progress.phase]} {progress.current}/{progress.total}
      {progress.filename ? ` · ${progress.filename}` : ''}</span>
    <div className="photo-progress-track"><div className="photo-progress-bar" style={{ width: `${percent}%` }} /></div>
  </div>;
}

export default function ImportStage({ pending, selectedSource, blocked, progress,
  groupTitle, onGroupTitle, groupNote, onGroupNote, fallbackDate, onFallbackDate,
  sharedLocation, onSharedLocation, onNoteToAll, onSelect, onMove, onCover,
  onImport, onCancel }: Props) {
  const single = pending.length === 1;
  const missingDate = pending.filter(p => !p.date).length;

  return <section className="panel photo-import">
    <h3>本次导入 · {pending.length} 张</h3>
    {single
      ? <p>单张作品：直接填写标题、拍摄信息，保存即可，不需要组标题。</p>
      : <p>已按拍摄时间排序，第一张为封面。可逐张编辑；整组标题和感受只在组内第一张展示。</p>}
    {!single && <>
      <div className="photo-fields">
        <label>整组标题<input value={groupTitle} disabled={blocked} onChange={e => onGroupTitle(e.target.value)} /></label>
        <label>缺失拍摄日期时补填<input type="date" value={fallbackDate} disabled={blocked} onChange={e => onFallbackDate(e.target.value)} /></label>
        <label>整组默认地点（城市 · 区县）<input value={sharedLocation} disabled={blocked} onChange={e => onSharedLocation(e.target.value)} /></label>
      </div>
      <label className="photo-wide-label">整组感受<textarea value={groupNote} disabled={blocked} rows={3}
        onChange={e => onGroupNote(e.target.value)} /></label>
      <div className="action-row">
        <button className="button ghost" disabled={blocked || !groupNote.trim()} onClick={onNoteToAll}>
          将组感受写入每张照片</button>
      </div>
    </>}
    <div className="photo-thumb-strip">
      {pending.map((item, index) => {
        const selected = item.source === selectedSource;
        return <div key={item.source}
          className={`photo-thumb-item ${index === 0 ? 'cover' : ''} ${selected ? 'selected' : ''}`}>
          <button className="photo-thumb-pick" disabled={blocked} title={item.filename}
            onClick={() => onSelect(item.source)}>
            <img src={item.thumb} alt={item.filename} loading="lazy" />
            <small>{item.filename}{!item.date ? ' · 缺少日期' : ''}</small>
          </button>
          {pending.length > 1 && <span className="photo-thumb-tools">
            {index === 0 ? <em>封面</em>
              : <button className="text-button" disabled={blocked} onClick={() => onCover(item.source)}>设为封面</button>}
            <button className="text-button" disabled={blocked || index === 0} aria-label={`前移 ${item.filename}`}
              onClick={() => onMove(item.source, -1)}>↑</button>
            <button className="text-button" disabled={blocked || index === pending.length - 1}
              aria-label={`后移 ${item.filename}`} onClick={() => onMove(item.source, 1)}>↓</button>
          </span>}
        </div>;
      })}
    </div>
    {missingDate > 0 && !single && <small>{missingDate} 张缺少拍摄日期，保存前请在下方补填。</small>}
    {progress && <Progress progress={progress} />}
    <div className="action-row">
      <button className="button primary" disabled={blocked || (!single && !groupTitle.trim())}
        onClick={onImport}>保存{single ? '' : '整组'}到本地</button>
      <button className="button ghost" disabled={blocked} onClick={onCancel}>取消本次导入</button>
    </div>
  </section>;
}
