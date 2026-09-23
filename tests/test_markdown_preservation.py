"""Markdown 空格/缩进/空行保留的回归测试。

Publisher 只应该改动 metadata 与图片语法，正文其余部分必须逐字符保留：
空行是段落语法，前导缩进是代码块/列表语法，都不能被 strip 或折叠。

注意：``str.splitlines()`` 会丢弃末尾换行，这符合预期（Markdown 末尾换行无语义），
本测试只断言有语义的中间空白。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from publisher.config import PublisherConfig
from publisher.parsers.metadata import clean_metadata
from publisher.processors.article import process_article


def make_config(vault: Path, project: Path) -> PublisherConfig:
    return PublisherConfig(
        vault=vault,
        project=project,
        output=project / "src/content/blog",
        image_output=project / "public/images/blog",
        cover_output=project / "public/images/covers",
    )


def _img(path: Path, mode: str = "RGB") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, (10, 10), (30, 30, 30)).save(path)
    return path


class CleanMetadataTest(unittest.TestCase):
    def test_strips_only_metadata_keeps_body_exact(self):
        source = (
            "**主题**：测试\n"
            "**时间**：2026-01-01\n"
            "**公开**：是\n"
            "----\n"
            "\n"
            "## 标题\n"
            "\n"
            "普通第一段。\n"
            "\n"
            "普通第二段。\n"
            "\n"
            "SOC：天玑700\n"
            "存储：8G + 128G\n"
            "电池：5000mah\n"
            "\n"
            "> blockquote line 1\n"
            "> blockquote line 2\n"
            "\n"
            "    indented line 1\n"
            "    indented line 2\n"
            "\n"
            "```python\n"
            'print("fenced code")\n'
            "```"
        )

        expected = (
            "## 标题\n"
            "\n"
            "普通第一段。\n"
            "\n"
            "普通第二段。\n"
            "\n"
            "SOC：天玑700\n"
            "存储：8G + 128G\n"
            "电池：5000mah\n"
            "\n"
            "> blockquote line 1\n"
            "> blockquote line 2\n"
            "\n"
            "    indented line 1\n"
            "    indented line 2\n"
            "\n"
            "```python\n"
            'print("fenced code")\n'
            "```"
        )

        self.assertEqual(clean_metadata(source), expected)

    def test_blank_lines_not_collapsed(self):
        source = "**公开**：是\n\n段落A\n\n段落B"
        self.assertEqual(clean_metadata(source), "段落A\n\n段落B")

    def test_single_newlines_not_expanded(self):
        # 单换行保持不变：既不能折叠成空格，也不能扩成空行。
        source = "**公开**：是\n\n行一\n行二\n行三"
        self.assertEqual(clean_metadata(source), "行一\n行二\n行三")

    def test_leading_indentation_preserved(self):
        # 正文以缩进代码块开头：前导空格必须保留。
        source = "**公开**：是\n\n    code line 1\n    code line 2"
        self.assertEqual(clean_metadata(source), "    code line 1\n    code line 2")


class ProcessArticleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vault = self.root / "vault"
        self.project = self.root / "project"
        self.vault.mkdir()
        self.config = make_config(self.vault, self.project)
        self.config.ensure_dirs()

    def tearDown(self):
        self.tmp.cleanup()

    def test_body_whitespace_preserved_end_to_end(self):
        _img(self.vault / "obsidian.png")
        _img(self.vault / "html.jpg")

        md_file = self.vault / "note.md"
        md_file.write_text(
            "**主题**：测试\n"
            "**时间**：2026-01-01\n"
            "**公开**：是\n"
            "\n"
            "普通第一段。\n"
            "\n"
            "普通第二段。\n"
            "\n"
            "SOC：天玑700\n"
            "存储：8G + 128G\n"
            "电池：5000mah\n"
            "\n"
            "> blockquote line 1\n"
            "> blockquote line 2\n"
            "\n"
            "    indented line 1\n"
            "    indented line 2\n"
            "\n"
            "```python\n"
            'print("fenced code")\n'
            "```\n"
            "\n"
            "![[obsidian.png|668]]\n"
            "\n"
            '<img src="html.jpg" width="680"> <p class="img-caption">caption</p>',
            encoding="utf-8",
        )

        article = process_article(md_file, md_file.read_text(encoding="utf-8"), self.config, log=lambda _: None)

        # 图片语法被转换（正文其余部分逐字符保留）
        self.assertIn('<img src="/images/blog/obsidian.webp" alt="obsidian.webp" width="668">', article.body)
        self.assertIn('<img src="/images/blog/html.webp" width="680">', article.body)
        self.assertIn('<p class="img-caption">caption</p>', article.body)

        # 空行（段落分隔）保留
        self.assertIn("普通第一段。\n\n普通第二段。", article.body)
        # 单换行保留（不折叠不扩行）
        self.assertIn("SOC：天玑700\n存储：8G + 128G\n电池：5000mah", article.body)
        # 引用块保留
        self.assertIn("> blockquote line 1\n> blockquote line 2", article.body)
        # 缩进代码块保留
        self.assertIn("    indented line 1\n    indented line 2", article.body)
        # 围栏代码块保留
        self.assertIn('```python\nprint("fenced code")\n```', article.body)


if __name__ == "__main__":
    unittest.main()
