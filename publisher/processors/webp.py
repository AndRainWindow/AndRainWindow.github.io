"""WebP 图片处理。

只负责：格式判断、尺寸读取、缩放、转 WebP、压缩、透明通道、EXIF orientation、
重复转换检测、文件大小统计。

不负责：查找附件、路径解析、引用修正（那些属于 image.py / cover.py）。

关系：
    image.py / cover.py
        ↓ 调用
    webp.py
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image, ImageOps

SUPPORTED_INPUT = {".png", ".jpg", ".jpeg", ".webp"}
SKIP_EXTENSIONS = {".gif", ".svg", ".ico"}

WEBP_PRESETS: dict[str, dict[str, int]] = {
    "blog": {"max_width": 2000, "quality": 82, "method": 6},
    "cover": {"max_width": 1600, "quality": 80, "method": 6},
    "photo": {"max_width": 2560, "quality": 85, "method": 6},
    "hero": {"max_width": 2560, "quality": 82, "method": 6},
}


def preset_for_path(path: str | Path) -> str:
    """根据目录路径自动选择 preset（用于迁移时判断）。"""
    p = str(path).replace("\\", "/")
    if "/covers/" in p or p.startswith("covers/"):
        return "cover"
    if "/photos/" in p or p.startswith("photos/"):
        return "photo"
    if "/home/" in p or p.startswith("home/"):
        return "hero"
    return "blog"


def _safe_name(name: str) -> str:
    """文件名里的空格统一替换成下划线（与 image.py 的 safe_name 行为一致）。"""
    return Path(name).name.replace(" ", "_")


class WebPProcessor:
    """把 PNG/JPG/JPEG/WEBP 转成 WebP，保留透明通道、修正 EXIF、按需缩放。"""

    def __init__(
        self,
        presets: Optional[dict[str, dict[str, int]]] = None,
        quality_overrides: Optional[dict[str, int]] = None,
    ):
        self.presets: dict[str, dict[str, int]] = {}
        for name, params in (presets or WEBP_PRESETS).items():
            self.presets[name] = dict(params)

        if quality_overrides:
            for key, value in quality_overrides.items():
                # blog_quality -> blog.quality
                if key.endswith("_quality"):
                    preset_name = key[: -len("_quality")]
                    if preset_name in self.presets:
                        self.presets[preset_name]["quality"] = int(value)

        # 记录已占用的目标文件名，用于同名冲突（abc.jpg / abc.png -> abc.webp）
        self._claimed: dict[str, Path] = {}

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def get_target_path(self, source_path: str | Path, output_dir: str | Path) -> Path:
        """计算目标 webp 路径，处理同名冲突。

        规则：空格 → 下划线，扩展名统一 .webp，保留 stem。
        同名冲突时（abc.jpg 与 abc.png 都要输出 abc.webp）：
            第二个文件用 ``abc_png.webp`` 这种带原扩展名后缀的名字。
        """
        source = Path(source_path)
        stem = source.stem.replace(" ", "_")
        target_name = f"{stem}.webp"

        # .webp 源的目标就是它自己（已经是最终格式），不参与同名冲突改名。
        # 否则迁移时会把已存在的 xxx.webp 误判成「与 xxx.jpg 冲突」而生成 xxx_webp.webp。
        if source.suffix.lower() == ".webp":
            return Path(output_dir) / target_name

        key = target_name.lower()
        resolved = source.resolve()
        if key in self._claimed and self._claimed[key] != resolved:
            ext_suffix = source.suffix.lower().lstrip(".")
            target_name = f"{stem}_{ext_suffix}.webp"
            key = target_name.lower()

        self._claimed[key] = resolved
        return Path(output_dir) / target_name

    def should_convert(self, source: Path, target: Path, max_width: int) -> bool:
        """判断是否需要（重新）转换。"""
        if not target.exists():
            return True

        # 目标就是源文件本身（已经是 webp）：只有尺寸超限才重压
        if source.suffix.lower() == ".webp" and target.resolve() == source.resolve():
            return self._image_width(source) > max_width

        # 目标已存在且比源新 → 跳过，避免每次发布重复压图
        return target.stat().st_mtime < source.stat().st_mtime

    def convert(
        self,
        source_path: str | Path,
        output_dir: str | Path,
        preset: str = "blog",
        max_width: Optional[int] = None,
        quality: Optional[int] = None,
        method: Optional[int] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> dict[str, Any]:
        """把一张图转成 WebP，返回结果字典。

        :return: 见 README / 模块文档。包含 source/output/filename/converted/skipped/
                 original_size/new_size。
        """
        source = Path(source_path)
        output_dir = Path(output_dir)
        log = log or (lambda msg: None)

        result: dict[str, Any] = {
            "source": str(source),
            "output": "",
            "filename": "",
            "converted": False,
            "skipped": False,
            "original_size": 0,
            "new_size": 0,
        }

        original_size = source.stat().st_size if source.exists() else 0
        result["original_size"] = original_size

        ext = source.suffix.lower()

        # 不处理的格式：保持原格式，返回原文件名
        if ext not in SUPPORTED_INPUT:
            result["filename"] = _safe_name(source.name)
            result["output"] = str(output_dir / result["filename"])
            result["new_size"] = original_size
            result["skipped"] = True
            return result

        params = dict(self.presets.get(preset, self.presets["blog"]))
        if max_width is not None:
            params["max_width"] = int(max_width)
        if quality is not None:
            params["quality"] = int(quality)
        if method is not None:
            params["method"] = int(method)

        target = self.get_target_path(source, output_dir)
        result["filename"] = target.name
        result["output"] = str(target)

        if not self.should_convert(source, target, params["max_width"]):
            result["new_size"] = target.stat().st_size if target.exists() else original_size
            result["skipped"] = True
            return result

        try:
            result["converted"] = self._encode(source, target, params)
            result["skipped"] = not result["converted"]
            result["new_size"] = target.stat().st_size if target.exists() else 0
        except Exception as exc:
            log(f"[WEBP] 转换失败 {source.name}: {exc}")
            # 回退：保持原格式，不转换
            result["filename"] = _safe_name(source.name)
            result["output"] = str(output_dir / result["filename"])
            result["new_size"] = original_size
            result["skipped"] = True

        return result

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _encode(self, source: Path, target: Path, params: dict[str, int]) -> bool:
        with Image.open(source) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            img = self._resize(img, params["max_width"])
            img = self._to_webp_mode(img)

            target.parent.mkdir(parents=True, exist_ok=True)

            # 先写临时文件再原子替换，避免「目标 == 源」时 Windows 文件占用问题。
            fd, tmp_path = tempfile.mkstemp(suffix=".webp", dir=str(target.parent))
            os.close(fd)
            try:
                img.save(tmp_path, "WEBP", quality=params["quality"], method=params["method"],
                         icc_profile=img.info.get("icc_profile", b""))
                os.replace(tmp_path, target)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        return True

    @staticmethod
    def _resize(img: Image.Image, max_width: int) -> Image.Image:
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = max(1, int(round(img.height * ratio)))
            return img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        return img

    @staticmethod
    def _to_webp_mode(img: Image.Image) -> Image.Image:
        """透明通道处理，避免简单 convert("RGB") 把透明图搞坏。"""
        mode = img.mode
        if mode == "RGBA":
            return img
        if mode == "LA":
            return img.convert("RGBA")
        if mode == "P" and "transparency" in img.info:
            return img.convert("RGBA")
        return img.convert("RGB")

    @staticmethod
    def _image_width(path: Path) -> int:
        try:
            with Image.open(path) as img:
                return img.width
        except Exception:
            return 0
