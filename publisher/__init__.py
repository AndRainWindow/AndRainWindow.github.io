"""AndRainWindow Publisher。

将 Obsidian Vault 中标记为「公开」的笔记发布为 Astro 博客内容。

模块划分：
- config.py        配置加载与保存（唯一允许读取 JSON 的地方）
- publisher.py     Publisher 核心调度器
- parsers/         纯解析（元数据、图片语法），不做 I/O
- processors/      图片复制、封面、字数统计、文章转换
- gui/             Tkinter 图形界面（仅界面层，不含发布逻辑）
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
