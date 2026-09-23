"""配置加载与保存。

其他模块不应该自己打开 JSON 文件——统一从这里读取。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PublisherConfig:
    """发布所需的所有配置。"""

    vault: Path
    project: Path
    output: Path
    image_output: Path
    cover_output: Path
    cover_override: dict[str, str] = field(default_factory=dict)
    webp: dict[str, Any] = field(default_factory=lambda: {"enabled": True})

    @classmethod
    def from_dict(cls, data: dict[str, Any], project_root: Path) -> "PublisherConfig":
        vault = Path(data["vault"])

        # 新格式有 project 字段；旧格式没有则用 config.json 所在目录作为项目根。
        project = Path(data["project"]) if data.get("project") else project_root
        if not project.is_absolute():
            project = project_root / project

        # 旧格式显式指定 output/image_output/cover_output 时优先使用，
        # 否则从 project 自动推导。
        def resolve(key: str, default_sub: str) -> Path:
            if data.get(key):
                path = Path(data[key])
                if not path.is_absolute():
                    path = project / path
                return path
            return project / default_sub

        return cls(
            vault=vault,
            project=project,
            output=resolve("output", "src/content/blog"),
            image_output=resolve("image_output", "public/images/blog"),
            cover_output=resolve("cover_output", "public/images/covers"),
            webp=data.get("webp", {"enabled": True}),
        )

    def ensure_dirs(self) -> None:
        for directory in (self.output, self.image_output, self.cover_output):
            directory.mkdir(parents=True, exist_ok=True)

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.vault.exists():
            problems.append(f"Obsidian Vault 不存在：{self.vault}")
        return problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "vault": str(self.vault),
            "project": str(self.project),
            "webp": dict(self.webp),
        }

    @property
    def webp_enabled(self) -> bool:
        return bool(self.webp.get("enabled", True))

    def webp_quality_overrides(self) -> dict[str, int]:
        """提取 ``blog_quality`` 这类质量覆盖项。"""
        return {
            key: int(value)
            for key, value in self.webp.items()
            if key.endswith("_quality") and isinstance(value, (int, float, str))
        }


def load_config(
    config_path: str | Path,
    site_config_path: str | Path | None = None,
) -> PublisherConfig:
    """读取 config.json（以及可选的 site_config.json）。"""
    config_path = Path(config_path)
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)

    project_root = config_path.parent
    config = PublisherConfig.from_dict(data, project_root)

    site_config = _load_site_config(site_config_path, project_root)
    config.cover_override = site_config.get("cover_override", {})

    return config


def save_config(config: PublisherConfig, config_path: str | Path) -> None:
    """保存 GUI 修改后的配置（只写 vault + project，输出目录由程序推导）。"""
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, ensure_ascii=False, indent=4)


def build_config(
    vault: str | Path,
    project: str | Path,
    cover_override: dict[str, str] | None = None,
) -> PublisherConfig:
    """根据 GUI 选择的两个路径直接构造配置，输出目录自动推导。"""
    project = Path(project)
    return PublisherConfig(
        vault=Path(vault),
        project=project,
        output=project / "src/content/blog",
        image_output=project / "public/images/blog",
        cover_output=project / "public/images/covers",
        cover_override=cover_override or {},
    )


def _load_site_config(
    site_config_path: str | Path | None,
    project_root: Path,
) -> dict[str, Any]:
    if site_config_path is None:
        site_config_path = project_root / "site_config.json"
    else:
        site_config_path = Path(site_config_path)

    if not site_config_path.exists():
        return {}

    with open(site_config_path, encoding="utf-8") as f:
        return json.load(f)
