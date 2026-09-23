"""Publisher 核心调度器。

负责扫描 Vault、判断「公开」、调用文章处理、写文件、汇报进度。
不包含 GUI 代码；通过回调让 CLI 与 GUI 复用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .config import PublisherConfig
from .parsers.metadata import get_field
from .processors.article import Article, build_astro_markdown, process_article
from .processors.webp import WebPProcessor

SKIP_FOLDERS = {"Attachments", ".obsidian", ".trash"}

ProgressCallback = Callable[[int, int], None]
LogCallback = Callable[[str], None]
FileCallback = Callable[[str], None]


@dataclass
class PublishResult:
    """一次发布的结果汇总。"""

    total: int = 0
    published: int = 0
    failed: int = 0
    skipped: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "发布完成",
            f"成功：{self.published}",
            f"失败：{self.failed}",
            f"跳过：{self.skipped}",
        ]
        return "\n".join(lines)


class Publisher:
    def __init__(
        self,
        config: PublisherConfig,
        on_progress: Optional[ProgressCallback] = None,
        on_log: Optional[LogCallback] = None,
        on_file: Optional[FileCallback] = None,
    ):
        self.config = config
        self.on_progress = on_progress or (lambda current, total: None)
        self.on_log = on_log or (lambda msg: print(msg))
        self.on_file = on_file or (lambda filename: None)

        # 一个共享的 WebP 处理器，跨笔记检测同名冲突（abc.jpg / abc.png → abc.webp）。
        self.webp: Optional[WebPProcessor] = None
        if config.webp_enabled:
            self.webp = WebPProcessor(quality_overrides=config.webp_quality_overrides())

        config.ensure_dirs()

    def publish_all(self) -> PublishResult:
        files = self._scan()
        result = PublishResult(total=len(files))

        self.on_progress(0, len(files))

        for index, md_file in enumerate(files, start=1):
            self._publish_one(md_file, result)
            self.on_progress(index, len(files))

        return result

    def publish_file(self, md_file: Path) -> Optional[Article]:
        """发布单个文件（主要用于测试与单篇重发）。"""
        result = PublishResult(total=1)
        return self._publish_one(md_file, result)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _scan(self) -> list[Path]:
        files: list[Path] = []
        for md_file in self.config.vault.rglob("*.md"):
            if any(folder in md_file.parts for folder in SKIP_FOLDERS):
                continue
            files.append(md_file)
        return files

    def _publish_one(self, md_file: Path, result: PublishResult) -> Optional[Article]:
        try:
            text = md_file.read_text(encoding="utf-8")
        except PermissionError:
            self.on_log(f"Skip: {md_file}")
            result.skipped += 1
            return None
        except Exception as exc:  # 读取失败视为该篇失败，继续下一篇
            result.failed += 1
            result.failures.append((md_file.name, str(exc)))
            self.on_log(f"[ERROR] {md_file.name}\n{exc}")
            return None

        if get_field(text, "公开") != "是":
            result.skipped += 1
            return None

        self.on_file(md_file.name)

        try:
            article = process_article(md_file, text, self.config, self.on_log, self.webp)
            article.output.parent.mkdir(parents=True, exist_ok=True)
            article.output.write_text(build_astro_markdown(article), encoding="utf-8")
            self.on_log(f"Published: {article.title}")
            result.published += 1
            return article
        except Exception as exc:
            result.failed += 1
            result.failures.append((md_file.name, str(exc)))
            self.on_log(f"[ERROR] {md_file.name}\n{exc}")
            return None
