"""完整文章内容转换流程。

处理顺序固定：

    原始 Obsidian Markdown
    → 修复旧错误 Markdown 图片
    → 转换 Obsidian 图片
    → 转换普通 Markdown 图片
    → 转换 HTML 图片
    → 删除顶部元数据
    → 统计
    → 生成 Astro frontmatter
    → 输出 Markdown
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from ..config import PublisherConfig
from ..parsers.metadata import clean_metadata, get_field
from .cover import get_cover
from .image import (
    process_html_images,
    process_markdown_images,
    process_obsidian_images,
    repair_old_markdown_images,
)
from .stats import count_words, reading_time
from .webp import WebPProcessor


@dataclass
class Article:
    """一篇文章处理完成后的完整结果。"""

    source: Path
    output: Path
    title: str
    date: str
    topics: str
    hero: str
    body: str
    word_count: int
    reading_time: int
    modified: str


def process_article(
    md_file: Path,
    text: str,
    config: PublisherConfig,
    log: Callable[[str], None] = print,
    webp: Optional[WebPProcessor] = None,
) -> Article:
    """把一篇 Obsidian 笔记转换成可输出的 Article 对象。"""
    title = md_file.stem
    date = get_field(text, "时间")
    topics = get_field(text, "主题")

    # 直接调用时也保证有一个共享的处理器（同名冲突检测）。
    if webp is None and config.webp_enabled:
        webp = WebPProcessor(quality_overrides=config.webp_quality_overrides())

    # 封面必须在转换之前、基于原始文本计算。
    hero = get_cover(title, text, md_file, config, log, webp)

    body = text
    body = repair_old_markdown_images(body, md_file, config, log, webp)
    body = process_obsidian_images(body, md_file, config, log, webp)
    body = process_markdown_images(body, md_file, config, log, webp)
    body = process_html_images(body, md_file, config, log, webp)
    body = clean_metadata(body)

    word_count = count_words(body)
    read_minutes = reading_time(word_count)

    modified = datetime.fromtimestamp(md_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    return Article(
        source=md_file,
        output=config.output / md_file.name,
        title=title,
        date=date,
        topics=topics,
        hero=hero,
        body=body,
        word_count=word_count,
        reading_time=read_minutes,
        modified=modified,
    )


def build_astro_markdown(article: Article) -> str:
    """把 Article 渲染成 Astro 内容集合需要的 frontmatter + 正文。"""
    title_yaml = json.dumps(article.title, ensure_ascii=False)
    updated_yaml = json.dumps(article.modified, ensure_ascii=False)
    topics_yaml = json.dumps(article.topics, ensure_ascii=False)
    hero_yaml = json.dumps(article.hero, ensure_ascii=False)

    return f"""---
title: {title_yaml}
date: {article.date}
updated: {updated_yaml}
topics: {topics_yaml}
heroImage: {hero_yaml}
wordCount: {article.word_count}
readingTime: {article.reading_time}
---

{article.body}
"""
