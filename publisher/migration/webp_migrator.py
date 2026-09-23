"""WebP 一次性迁移工具。

两阶段：
    Phase A —— migrate()：扫描 public/images，把 PNG/JPG/JPEG 转成 WebP，
                更新 src/ 与 site_config.json 里的引用，写 migration_report.json。
    Phase B —— cleanup()：确认 ``npm run build`` 成功后再调用，
                删除已经被 .webp 替代的原图。

安全边界：
    - 只更新 ``/images/...`` 与 ``public/images/...`` 形式的引用，绝不碰外链。
    - cleanup 前会校验对应的 .webp 确实存在，缺了就不删。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from ..processors.webp import SUPPORTED_INPUT, WebPProcessor, preset_for_path

# 引用里可能写图片路径的文本文件扩展名
_TEXT_EXTENSIONS = {
    ".md", ".mdx", ".astro", ".ts", ".tsx", ".js", ".jsx",
    ".json", ".css", ".html", ".htm", ".scss",
}


class WebPMigrator:
    def __init__(
        self,
        project: str | Path,
        quality_overrides: Optional[dict[str, int]] = None,
        log: Callable[[str], None] = print,
    ):
        self.project = Path(project)
        self.log = log
        self.images_dir = self.project / "public" / "images"
        self.webp = WebPProcessor(quality_overrides=quality_overrides)

    # ------------------------------------------------------------------
    # Phase A
    # ------------------------------------------------------------------

    def migrate(self) -> dict:
        if not self.images_dir.exists():
            raise FileNotFoundError(f"未找到图片目录：{self.images_dir}")

        files: list[dict] = []
        to_delete: list[dict] = []
        url_map: dict[str, str] = {}
        path_map: dict[str, str] = {}

        for source in sorted(self.images_dir.rglob("*")):
            if not source.is_file():
                continue

            ext = source.suffix.lower()
            if ext not in SUPPORTED_INPUT:
                if ext in {".gif", ".svg", ".ico"}:
                    self.log(f"[MIGRATE] 跳过 {source.name}（{ext} 不转换）")
                continue

            preset = preset_for_path(source)
            result = self.webp.convert(source, source.parent, preset=preset, log=self.log)
            new_name = result["filename"]
            target = source.parent / new_name

            rel = source.relative_to(self.images_dir).as_posix()
            new_rel = target.relative_to(self.images_dir).as_posix()

            if ext == ".webp":
                # 已是 webp：可能因超宽被原地重压，但文件名不变，引用无需更新。
                if result["converted"]:
                    files.append(self._entry(rel, new_rel, result))
                    self.log(f"[MIGRATE] 重压 {rel}")
                continue

            url_map[f"/images/{rel}"] = f"/images/{new_rel}"
            path_map[f"public/images/{rel}"] = f"public/images/{new_rel}"
            to_delete.append({"source": rel, "target": new_rel})
            files.append(self._entry(rel, new_rel, result))

            if result["converted"]:
                self.log(f"[MIGRATE] 转换 {rel} -> {new_rel}")
            else:
                self.log(f"[MIGRATE] 已存在，跳过 {rel} -> {new_rel}")

        ref_files = self._update_references({**url_map, **path_map})

        report = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "images_dir": "public/images",
            "summary": {
                "total": len(files),
                "converted": sum(1 for f in files if f["converted"]),
                "skipped": sum(1 for f in files if not f["converted"]),
                "references_updated_files": len(ref_files),
                "to_delete": len(to_delete),
            },
            "files": files,
            "to_delete": to_delete,
            "references_updated_files": ref_files,
        }

        report_path = self.project / "migration_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log(f"[MIGRATE] 报告已写入 {report_path.name}")

        return report

    # ------------------------------------------------------------------
    # Phase B
    # ------------------------------------------------------------------

    def cleanup(self) -> dict:
        report_path = self.project / "migration_report.json"
        if not report_path.exists():
            raise FileNotFoundError("未找到 migration_report.json，请先运行 --migrate")

        report = json.loads(report_path.read_text(encoding="utf-8"))

        deleted: list[str] = []
        for entry in report.get("to_delete", []):
            source_path = self.images_dir / entry["source"]
            replacement = self.images_dir / entry["target"]

            if not source_path.exists():
                continue
            if not replacement.exists():
                self.log(f"[CLEANUP] 跳过 {entry['source']}（对应 .webp 不存在）")
                continue

            source_path.unlink()
            deleted.append(entry["source"])
            self.log(f"[CLEANUP] 删除 {entry['source']}")

        return {"deleted": deleted, "count": len(deleted)}

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _entry(rel: str, new_rel: str, result: dict) -> dict:
        return {
            "source": rel,
            "target": new_rel,
            "converted": bool(result["converted"]),
            "original_size": result.get("original_size", 0),
            "new_size": result.get("new_size", 0),
        }

    def _update_references(self, mapping: dict[str, str]) -> list[str]:
        if not mapping:
            return []

        # 长的 key 先替换，避免子串相互覆盖。
        # 负向前瞻：/images/ 前不能是 URL/主机名里的字符，避免把外链里的路径也改掉。
        entries = [
            (re.compile(r"(?<![\w./:%?&=#-])" + re.escape(old)), new)
            for old, new in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)
        ]

        updated: list[str] = []
        for path in self._reference_files():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            original = text
            for pattern, new in entries:
                text = pattern.sub(new, text)

            if text != original:
                path.write_text(text, encoding="utf-8")
                rel = path.relative_to(self.project).as_posix()
                updated.append(rel)
                self.log(f"[MIGRATE] 更新引用 {rel}")

        return updated

    def _reference_files(self) -> list[Path]:
        files: list[Path] = []

        src_dir = self.project / "src"
        if src_dir.exists():
            for p in src_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in _TEXT_EXTENSIONS:
                    files.append(p)

        site_config = self.project / "site_config.json"
        if site_config.exists():
            files.append(site_config)

        return files
