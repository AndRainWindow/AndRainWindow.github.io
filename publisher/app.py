"""应用门面：把配置加载与 Publisher 编排在一起，供 CLI 和 GUI 复用。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .config import PublisherConfig, load_config, save_config
from .publisher import Publisher, PublishResult

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config.json"
DEFAULT_SITE_CONFIG = PROJECT_ROOT / "site_config.json"


class PublisherApp:
    def __init__(
        self,
        config: PublisherConfig,
        config_path: Optional[Path] = None,
        site_config_path: Optional[Path] = None,
    ):
        self.config = config
        self.config_path = config_path
        self.site_config_path = site_config_path

    @classmethod
    def from_config_files(
        cls,
        config_path: str | Path,
        site_config_path: str | Path | None = None,
    ) -> "PublisherApp":
        config = load_config(config_path, site_config_path)
        return cls(
            config,
            Path(config_path),
            Path(site_config_path) if site_config_path else None,
        )

    def publish(
        self,
        on_progress=None,
        on_log=None,
        on_file=None,
    ) -> PublishResult:
        publisher = Publisher(
            self.config,
            on_progress=on_progress,
            on_log=on_log,
            on_file=on_file,
        )
        return publisher.publish_all()

    def save_config(self) -> None:
        if self.config_path:
            save_config(self.config, self.config_path)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_publisher.py",
        description="AndRainWindow Publisher：将 Obsidian 公开笔记发布为 Astro 博客内容",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="config.json 路径")
    parser.add_argument("--site-config", default=str(DEFAULT_SITE_CONFIG), help="site_config.json 路径")
    parser.add_argument("--gui", action="store_true", help="启动图形界面")
    parser.add_argument("--migrate", action="store_true", help="把 public/images 一次性迁移成 WebP（含引用更新）")
    parser.add_argument("--cleanup", action="store_true", help="npm run build 成功后，删除被 .webp 替代的原图")
    args = parser.parse_args(argv)

    if args.gui:
        from .gui.main_window import launch_gui

        return launch_gui(args.config, args.site_config)

    app = PublisherApp.from_config_files(args.config, args.site_config)

    if args.migrate:
        return _run_migrate(app)

    if args.cleanup:
        return _run_cleanup(app)

    problems = app.config.validate()
    if problems:
        for problem in problems:
            print(f"[ERROR] {problem}")
        return 1

    result = app.publish(on_log=print)

    print()
    print(result.summary())

    for filename, reason in result.failures:
        print(f"[失败] {filename}: {reason}")

    return 0 if result.failed == 0 else 1


def _run_migrate(app: PublisherApp) -> int:
    import json

    from .migration.webp_migrator import WebPMigrator

    migrator = WebPMigrator(
        app.config.project,
        quality_overrides=app.config.webp_quality_overrides(),
        log=print,
    )

    try:
        report = migrator.migrate()
    except Exception as exc:
        print(f"[ERROR] 迁移失败：{exc}")
        return 1

    print()
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("迁移完成。确认 npm run build 成功后，运行 --cleanup 删除原图。")
    return 0


def _run_cleanup(app: PublisherApp) -> int:
    from .migration.webp_migrator import WebPMigrator

    migrator = WebPMigrator(app.config.project, log=print)

    try:
        result = migrator.cleanup()
    except Exception as exc:
        print(f"[ERROR] 清理失败：{exc}")
        return 1

    print()
    print(f"已删除 {result['count']} 个原图文件。")
    return 0
