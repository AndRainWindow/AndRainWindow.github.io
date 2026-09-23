"""文章封面处理。

优先级：site_config.json 手动指定 → 正文第一张图片 → default.webp。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from ..config import PublisherConfig
from ..parsers.images import find_first_image
from .image import copy_or_convert, find_attachment, normalize_public_path
from .webp import WebPProcessor

DEFAULT_COVER = "/images/covers/default.webp"


def process_cover(
    image: str,
    md_file: Path,
    config: PublisherConfig,
    log: Callable[[str], None] = print,
    webp: Optional[WebPProcessor] = None,
) -> str:
    if not image:
        return DEFAULT_COVER

    # 防止旧格式 xxx.jpg|668
    image = re.sub(r"\|\d+$", "", image)

    source = find_attachment(md_file, image, config.vault)

    if not source:
        log(f"Missing cover image: {image}")
        return DEFAULT_COVER

    new_name = copy_or_convert(source, config.cover_output, "cover", config, log, webp)
    log(f"Copy cover: {new_name}")

    return f"/images/covers/{new_name}"


def get_cover(
    title: str,
    text: str,
    md_file: Path,
    config: PublisherConfig,
    log: Callable[[str], None] = print,
    webp: Optional[WebPProcessor] = None,
) -> str:
    if title in config.cover_override:
        log(f"Use custom cover: {title}")
        return normalize_public_path(config.cover_override[title])

    image = find_first_image(text)

    if image:
        return process_cover(image, md_file, config, log, webp)

    return DEFAULT_COVER
