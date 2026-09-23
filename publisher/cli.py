"""JSONL CLI bridge for the Tauri desktop app.

Business logic stays in the existing Publisher modules. This module only adapts
callbacks/results to a stable line-delimited JSON protocol for native clients.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .app import DEFAULT_CONFIG, DEFAULT_SITE_CONFIG, PublisherApp
from .config import load_config


def emit(event_type: str, **payload: Any) -> None:
    print(json.dumps({"type": event_type, **payload}, ensure_ascii=False), flush=True)


def emit_log(message: str, level: str = "info") -> None:
    emit("log", level=level, message=message)


def _load_app(args: argparse.Namespace) -> PublisherApp:
    return PublisherApp.from_config_files(args.config, args.site_config)


def command_config(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config, args.site_config)
    except Exception as exc:
        emit("error", message=f"读取配置失败：{exc}")
        return 2

    emit(
        "config",
        vault=str(config.vault),
        project=str(config.project),
        webpEnabled=config.webp_enabled,
        webp=dict(config.webp),
    )
    return 0


def command_validate(args: argparse.Namespace) -> int:
    try:
        app = _load_app(args)
    except Exception as exc:
        emit("error", message=f"读取配置失败：{exc}")
        return 2

    problems = list(app.config.validate())
    if not app.config.project.exists():
        problems.append(f"Astro 项目不存在：{app.config.project}")
    elif not (app.config.project / "package.json").exists():
        problems.append(f"目录不是有效的 Astro 项目：{app.config.project}")

    emit("validation", ok=not problems, problems=problems)
    return 0 if not problems else 2


def command_publish(args: argparse.Namespace) -> int:
    try:
        app = _load_app(args)
    except Exception as exc:
        emit("error", message=f"读取配置失败：{exc}")
        return 2

    problems = app.config.validate()
    if problems:
        emit("error", message="；".join(problems))
        return 2

    emit("start", task="publish")
    result = app.publish(
        on_progress=lambda current, total: emit(
            "progress", current=current, total=total
        ),
        on_log=emit_log,
        on_file=lambda filename: emit("file", filename=filename),
    )

    emit(
        "complete",
        task="publish",
        total=result.total,
        success=result.published,
        failed=result.failed,
        skipped=result.skipped,
        failures=[{"file": name, "reason": reason} for name, reason in result.failures],
    )
    return 0 if result.failed == 0 else 1


def command_migrate(args: argparse.Namespace) -> int:
    try:
        app = _load_app(args)
        from .migration.webp_migrator import WebPMigrator

        emit("start", task="migrate-webp")
        migrator = WebPMigrator(
            app.config.project,
            quality_overrides=app.config.webp_quality_overrides(),
            log=emit_log,
        )
        report = migrator.migrate()
        emit("complete", task="migrate-webp", summary=report.get("summary", {}))
        return 0
    except Exception as exc:
        emit("error", message=f"WebP 迁移失败：{exc}")
        return 1


def command_cleanup(args: argparse.Namespace) -> int:
    try:
        app = _load_app(args)
        from .migration.webp_migrator import WebPMigrator

        emit("start", task="cleanup-webp")
        migrator = WebPMigrator(app.config.project, log=emit_log)
        result = migrator.cleanup()
        emit("complete", task="cleanup-webp", count=result.get("count", 0))
        return 0
    except Exception as exc:
        emit("error", message=f"WebP 清理失败：{exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m publisher.cli")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--site-config", default=str(DEFAULT_SITE_CONFIG))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config")
    sub.add_parser("validate")
    sub.add_parser("publish")
    sub.add_parser("migrate-webp")
    sub.add_parser("cleanup-webp")
    photos = sub.add_parser("photos")
    photos.add_argument("--project", required=True)
    return parser


def command_photos(args: argparse.Namespace) -> int:
    try:
        from .photos.service import dispatch
        payload = json.load(sys.stdin)

        def emit_progress(event: dict) -> None:
            # Contract: N progress lines, then exactly one terminal line.
            emit("photo_progress", **event)

        result = dispatch(Path(args.project), payload, emit_progress)
        emit("photo_result", result=result)
        return 0
    except Exception as exc:
        emit("error", message=str(exc))
        return 1


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    args = build_parser().parse_args(argv)
    handlers = {
        "config": command_config,
        "validate": command_validate,
        "publish": command_publish,
        "migrate-webp": command_migrate,
        "cleanup-webp": command_cleanup,
        "photos": command_photos,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
