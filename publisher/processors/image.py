"""图片处理：查找附件、复制/转 WebP、生成网站路径，以及各类图片语法的转换。

关系：
    image.py ——调用——> webp.py

webp.py 只负责「把一张图转成 WebP」；这里负责「找到图、决定复制还是转、修正引用」。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable, Optional

from ..config import PublisherConfig
from ..parsers.images import parse_obsidian_image
from .webp import WebPProcessor


def safe_name(name: str) -> str:
    """取文件名并把空格替换成下划线。"""
    return Path(name).name.replace(" ", "_")


def normalize_public_path(path: str) -> str:
    """把 ``public/images/...`` 或相对路径统一成 ``/images/...`` 形式的 URL。"""
    path = str(path).replace("\\", "/").strip()

    if path.startswith("public/"):
        path = "/" + path[len("public/"):]

    if not path.startswith("/"):
        path = "/" + path

    return path


def find_attachment(md_file: Path, filename: str, vault: Path) -> Optional[Path]:
    """按固定顺序查找附件：同目录 → Attachments → 父目录 → 整个 vault。"""
    filename = Path(filename).name

    paths = [
        md_file.parent / filename,
        md_file.parent / "Attachments" / filename,
        vault / "Attachments" / filename,
    ]

    for parent in md_file.parents:
        paths.append(parent / "Attachments" / filename)

    for path in paths:
        if path.exists() and path.is_file():
            return path

    for path in vault.rglob(filename):
        if ".obsidian" in path.parts or ".trash" in path.parts:
            continue
        if path.is_file():
            return path

    return None


def copy_or_convert(
    source: Path,
    output_dir: Path,
    preset: str,
    config: PublisherConfig,
    log: Callable[[str], None],
    webp: Optional[WebPProcessor],
) -> str:
    """复制原图或转成 WebP，返回最终文件名。"""
    if config.webp_enabled:
        processor = webp or WebPProcessor(quality_overrides=config.webp_quality_overrides())
        result = processor.convert(source, output_dir, preset=preset, log=log)
        name = result["filename"]
        if not result["converted"]:
            # 跳过（已存在）或无法转换：确保目标文件存在
            target = output_dir / name
            if not target.exists():
                shutil.copy2(source, target)
        return name

    name = safe_name(source.name)
    shutil.copy2(source, output_dir / name)
    return name


def copy_blog_image(
    md_file: Path,
    filename: str,
    config: PublisherConfig,
    log: Callable[[str], None] = print,
    webp: Optional[WebPProcessor] = None,
) -> Optional[str]:
    """找图并复制/转 WebP 到 public/images/blog，返回网站 URL；找不到返回 None。"""
    filename = Path(filename).name
    source = find_attachment(md_file, filename, config.vault)

    if not source:
        return None

    new_name = copy_or_convert(source, config.image_output, "blog", config, log, webp)
    log(f"Copy image: {new_name}")

    return f"/images/blog/{new_name}"


# =========================
# 修复旧脚本留下的错误 Markdown
# =========================

_OLD_MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*?)\|(\d+)\]\(([^)]+?)\|(\d+)\)")


def repair_old_markdown_images(
    text: str,
    md_file: Path,
    config: PublisherConfig,
    log: Callable[[str], None] = print,
    webp: Optional[WebPProcessor] = None,
) -> str:
    """修复旧脚本生成出来的 ``![abc.png|668](/images/blog/abc.png|668)``。"""
    def replace_image(match: re.Match) -> str:
        alt_with_name = match.group(1).strip()
        width = match.group(2)
        raw_src = match.group(3).strip()

        filename = Path(raw_src).name
        if not filename:
            filename = alt_with_name

        clean_name = safe_name(filename)
        source = find_attachment(md_file, clean_name, config.vault)

        if source:
            new_name = copy_or_convert(source, config.image_output, "blog", config, log, webp)
            log(f"Repair old image: {new_name}")
        else:
            new_name = clean_name
            log(f"Old image source not found: {clean_name}")

        url = f"/images/blog/{new_name}"
        return f'<img src="{url}" alt="{new_name}" width="{width}">'

    return _OLD_MARKDOWN_IMAGE.sub(replace_image, text)


# =========================
# Obsidian wiki 图片
# =========================

_OBSIDIAN_IMAGE = re.compile(r"!\[\[([^\]]+)\]\]")


def process_obsidian_images(
    text: str,
    md_file: Path,
    config: PublisherConfig,
    log: Callable[[str], None] = print,
    webp: Optional[WebPProcessor] = None,
) -> str:
    """``![[abc.png]]`` → ``![abc.webp](/images/blog/abc.webp)``；带宽度则输出 <img>。"""
    def replace_image(match: re.Match) -> str:
        raw = match.group(1)
        filename, width = parse_obsidian_image(raw)

        url = copy_blog_image(md_file, filename, config, log, webp)

        if not url:
            log(f"Missing image: {filename}")
            url = f"/images/blog/{safe_name(filename)}"

        display_name = Path(url).name

        if width:
            return f'<img src="{url}" alt="{display_name}" width="{width}">'

        return f"![{display_name}]({url})"

    return _OBSIDIAN_IMAGE.sub(replace_image, text)


# =========================
# 普通 Markdown 图片
# =========================

_MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def process_markdown_images(
    text: str,
    md_file: Path,
    config: PublisherConfig,
    log: Callable[[str], None] = print,
    webp: Optional[WebPProcessor] = None,
) -> str:
    """处理普通 Markdown 相对图片；已经是 /images/ 或 http(s):// 的不改。"""
    def replace_image(match: re.Match) -> str:
        alt = match.group(1)
        src = match.group(2).strip()

        if (
            src.startswith("/")
            or src.startswith("http://")
            or src.startswith("https://")
            or src.startswith("//")
            or src.startswith("data:")
        ):
            return match.group(0)

        src = re.sub(r"\|\d+$", "", src)
        filename = Path(src).name

        url = copy_blog_image(md_file, filename, config, log, webp)

        if not url:
            log(f"Missing Markdown image: {filename}")
            return match.group(0)

        return f"![{alt}]({url})"

    return _MARKDOWN_IMAGE.sub(replace_image, text)


# =========================
# HTML 图片
# =========================

_HTML_IMAGE = re.compile(r'(<img\b[^>]*?\bsrc=["\'])([^"\']+)(["\'][^>]*>)', re.IGNORECASE)


def process_html_images(
    text: str,
    md_file: Path,
    config: PublisherConfig,
    log: Callable[[str], None] = print,
    webp: Optional[WebPProcessor] = None,
) -> str:
    """``<img src="abc.jpg" width="680">`` → ``<img src="/images/blog/abc.webp" ...>``。

    紧跟在后面的 ``<p class="img-caption">...</p>`` 完全保留。
    """
    def replace_image(match: re.Match) -> str:
        prefix = match.group(1)
        src = match.group(2).strip()
        suffix = match.group(3)

        if (
            src.startswith("/")
            or src.startswith("http://")
            or src.startswith("https://")
            or src.startswith("//")
            or src.startswith("data:")
        ):
            return match.group(0)

        filename = Path(src).name

        url = copy_blog_image(md_file, filename, config, log, webp)

        if not url:
            log(f"Missing HTML image: {filename}")
            return match.group(0)

        return prefix + url + suffix

    return _HTML_IMAGE.sub(replace_image, text)
