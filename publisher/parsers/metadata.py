"""解析 Obsidian 顶部的元数据字段。

支持的格式（冒号或全角冒号均可）：

    **主题**：Android, ADB
    **时间**：2026-09-14
    **公开**：是
"""

from __future__ import annotations

import re


def get_field(text: str, name: str) -> str:
    """从文本中提取 ``**name**:value`` 形式的字段值。"""
    match = re.search(rf"\*\*{re.escape(name)}\*\*[:：](.*)", text)
    return match.group(1).strip() if match else ""


def parse_metadata(text: str) -> dict[str, str]:
    """一次性解析所有已知元数据字段。"""
    return {
        "主题": get_field(text, "主题"),
        "时间": get_field(text, "时间"),
        "公开": get_field(text, "公开"),
        "封面": get_field(text, "封面"),
    }


_METADATA_LINE = re.compile(r"^\s*\*\*(主题|时间|公开|封面)\*\*[:：]")
_DIVIDER_LINE = re.compile(r"[-—–_\s]{3,}")


def clean_metadata(text: str) -> str:
    """去掉正文顶部的元数据块、空行和分隔线，返回干净正文。"""
    lines = text.splitlines()

    while lines and not lines[0].strip():
        lines.pop(0)

    while lines:
        line = lines[0].strip()

        if not line:
            lines.pop(0)
            continue

        if _METADATA_LINE.match(line):
            lines.pop(0)
            continue

        if _DIVIDER_LINE.fullmatch(line):
            lines.pop(0)
            continue

        break

    return "\n".join(lines).strip()
