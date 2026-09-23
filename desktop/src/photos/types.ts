// 摄影管理的共享类型。扁平行（PhotoRow）与 Python 端 photos.json 的行一一对应；
// 组只是视图概念（见 groups.ts），存储端始终是扁平行 + 冗余的组字段。

export type Selection =
  | { type: 'group'; groupId: string }
  | { type: 'photo'; groupId: string; photoId: string };

/** photos.json 的一行，或导入前（inspect）的一个待导入项。 */
export interface PhotoRow {
  id?: string;
  source?: string;
  filename?: string;
  image?: string;
  thumb?: string;
  title: string;
  note: string;
  date: string;
  location: string;
  camera?: string;
  lens?: string;
  iso?: string;
  aperture?: string;
  shutter?: string;
  focalLength?: string;
  utcOffset?: string;
  order?: number;
  province?: string;
  city?: string;
  district?: string;
  groupId?: string;
  groupTitle?: string;
  groupNote?: string;
  hidden?: boolean;
  deleted?: boolean;
  groupHidden?: boolean;
  groupDeleted?: boolean;
  gps?: { lat: number; lon: number } | null;
  hasGps?: boolean;
  locationSource?: string;
}

/** 本次导入的待导入项：一定有 source/filename/thumb（来自 inspect）。 */
export interface PendingPhoto extends PhotoRow {
  source: string;
  filename: string;
  thumb: string;
}

export interface PhotoGroup {
  id: string;
  title: string;
  note: string;
  /** 组日期 = 封面（第一张）照片的拍摄日期。 */
  date: string;
  hidden: boolean;
  deleted: boolean;
  photos: PhotoRow[];
  cover: PhotoRow;
}

export type ImportPhase = 'inspect' | 'convert' | 'geocode' | 'finalize';

export interface PhotoEvent {
  phase: ImportPhase;
  current: number;
  total: number;
  filename?: string;
  taskId?: string;
}

export const PHASE_LABELS: Record<ImportPhase, string> = {
  inspect: '读取拍摄参数',
  convert: '转换 WebP',
  geocode: '识别地点',
  finalize: '写入目录',
};

export interface GeoState {
  configured: boolean;
  provider: string;
  geoapify: boolean;
  amap: boolean;
}

export interface BridgeResult {
  photos?: PhotoRow[];
  selection?: PendingPhoto[];
  errors?: string[];
  thumbnail?: string;
  location?: string;
  locationSource?: string;
  url?: string;
  message?: string;
  configured?: boolean;
  provider?: string;
  geoapify?: boolean;
  amap?: boolean;
}
