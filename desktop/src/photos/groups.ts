// 把扁平行组装成 组→照片 视图模型，以及导入排序 / 图片地址工具。
import { convertFileSrc } from '@tauri-apps/api/core';
import type { PendingPhoto, PhotoGroup, PhotoRow } from './types';

/** 组内排序：全部成员都有 order 时按 order 升序（封面为 0），否则按拍摄日期降序（旧行为）。 */
function orderedMembers(members: PhotoRow[]): PhotoRow[] {
  const copy = [...members];
  if (copy.every(p => typeof p.order === 'number' && Number.isInteger(p.order))) {
    copy.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  } else {
    copy.sort((a, b) => String(b.date).localeCompare(String(a.date)));
  }
  return copy;
}

export function toGroups(rows: PhotoRow[]): PhotoGroup[] {
  const map = new Map<string, PhotoRow[]>();
  for (const row of rows) {
    const id = row.groupId || row.id || '';
    if (!map.has(id)) map.set(id, []);
    map.get(id)!.push(row);
  }
  const groups: PhotoGroup[] = [];
  for (const [id, members] of map) {
    const photos = orderedMembers(members);
    const cover = photos[0];
    groups.push({
      id,
      title: cover.groupTitle || '',
      note: cover.groupNote || '',
      date: cover.date,
      hidden: Boolean(cover.groupHidden),
      deleted: Boolean(cover.groupDeleted),
      photos,
      cover,
    });
  }
  // 库列表：新组在前（组日期 = 封面日期）。
  return groups.sort((a, b) => String(b.date).localeCompare(String(a.date)));
}

/** 照片库计数：排除回收站（组与照片各自计数）。 */
export function libraryCounts(rows: PhotoRow[]): { groups: number; photos: number } {
  const alive = rows.filter(p => !p.deleted && !p.groupDeleted);
  return {
    groups: new Set(alive.map(p => p.groupId || p.id || '')).size,
    photos: alive.length,
  };
}

/** 导入排序：拍摄时间升序（封面=最早一张），缺日期的垫底；同秒保持选择顺序。 */
export function sortForImport<T extends PhotoRow>(items: T[]): T[] {
  return [...items].sort((a, b) => String(a.date || '9999').localeCompare(String(b.date || '9999')));
}

/**
 * 已发布 WebP 的库内预览地址。走自定义 photolibrary 协议（Rust 侧白名单校验）；
 * 非 Tauri 环境（Playwright 桩）没有 convertFileSrc，返回 null 由调用方渲染占位。
 */
export function libraryImageSrc(image: string | undefined): string | null {
  const name = (image || '').split('/').pop();
  if (!name) return null;
  const internals = (window as unknown as { __TAURI_INTERNALS__?: { convertFileSrc?: unknown } }).__TAURI_INTERNALS__;
  if (!internals?.convertFileSrc) return null;
  try {
    return convertFileSrc(name, 'photolibrary');
  } catch {
    return null;
  }
}

/** 待导入项的缩略图：inspect 自带的 320px data URL，零额外请求。 */
export function pendingThumbSrc(photo: PendingPhoto | PhotoRow): string | null {
  return photo.thumb || null;
}
