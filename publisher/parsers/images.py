"""识别各类图片语法。

只负责「解析出图片信息」，不复制文件。

支持：
- ``![[abc.png]]``
- ``![[abc.png|668]]``
- ``![alt](abc.png)``
- 旧版本错误生成的 ``![abc.png|668](/images/blog/abc.png|668)``
- HTML ``<img src="abc.jpg" width="680">``
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ImageReference:
    """统一的内部图片引用对象。"""

    filename: str
    width: Optional[str] = None
    source_type: str = "obsidian"  # obsidian | markdown | html | old_markdown


def parse_obsidian_image(raw: str) -> tuple[str, Optional[str]]:
    """把 ``abc.png`` 或 ``abc.png|668`` 解析成 ``(filename, width)``。"""
    parts = raw.split("|", 1)

    filename = parts[0].strip()
    width: Optional[str] = None

    if len(parts) > 1:
        option = parts[1].strip()
        if option.isdigit():
            width = option

    return filename, width


def find_first_image(text: str) -> Optional[str]:
    """返回正文第一张图片的文件名（用于封面），找不到返回 None。"""
    wiki = re.search(r"!\[\[([^\]]+)\]\]", text)

    if wiki:
        filename, _ = parse_obsidian_image(wiki.group(1))
        return filename

    markdown = re.search(r"!\[[^\]]*\]\(([^)]+)\)", text)

    if markdown:
        src = markdown.group(1).strip()
        # 兼容旧脚本生成的 xxx.png|668
        src = re.sub(r"\|\d+$", "", src)
        return Path(src).name

    return None
