"""WebP 图片处理层与迁移工具的测试。

只依赖标准库 unittest，不依赖 pytest。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from publisher.config import PublisherConfig
from publisher.migration.webp_migrator import WebPMigrator
from publisher.processors import cover, image
from publisher.processors.webp import WEBP_PRESETS, WebPProcessor, preset_for_path


def make_image(path: Path, size=(100, 100), mode="RGB", color=(30, 30, 30)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode in ("P",):
        img = Image.new("P", size)
    elif mode == "LA":
        img = Image.new("LA", size, (200, 128))
    elif mode == "RGBA":
        img = Image.new("RGBA", size, color + (128,))
    else:
        img = Image.new(mode, size, color)
    img.save(path)
    return path


def make_config(vault: Path, project: Path) -> PublisherConfig:
    return PublisherConfig(
        vault=vault,
        project=project,
        output=project / "src/content/blog",
        image_output=project / "public/images/blog",
        cover_output=project / "public/images/covers",
    )


class WebPProcessorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / "src"
        self.out = self.root / "out"
        self.src.mkdir()
        self.out.mkdir()
        self.processor = WebPProcessor()

    def tearDown(self):
        self.tmp.cleanup()

    def test_presets_exist(self):
        for name, params in WEBP_PRESETS.items():
            self.assertEqual(params["method"], 6)
            self.assertIn("max_width", params)
            self.assertIn("quality", params)

    def test_preset_for_path(self):
        self.assertEqual(preset_for_path("public/images/covers/x.jpg"), "cover")
        self.assertEqual(preset_for_path("public/images/photos/x.jpg"), "photo")
        self.assertEqual(preset_for_path("public/images/home/x.jpg"), "hero")
        self.assertEqual(preset_for_path("public/images/blog/x.jpg"), "blog")

    def test_jpg_converts_to_webp(self):
        make_image(self.src / "a.jpg", mode="RGB")
        result = self.processor.convert(self.src / "a.jpg", self.out, preset="blog")
        self.assertTrue(result["converted"])
        self.assertEqual(result["filename"], "a.webp")
        self.assertTrue((self.out / "a.webp").exists())

    def test_png_rgb_converts(self):
        make_image(self.src / "b.png", mode="RGB")
        result = self.processor.convert(self.src / "b.png", self.out)
        self.assertTrue(result["converted"])
        self.assertEqual(result["filename"], "b.webp")

    def test_jpeg_converts(self):
        make_image(self.src / "c.jpeg", mode="RGB")
        result = self.processor.convert(self.src / "c.jpeg", self.out)
        self.assertTrue(result["converted"])
        self.assertEqual(result["filename"], "c.webp")

    def test_transparent_rgba_preserved(self):
        make_image(self.src / "t.png", mode="RGBA", color=(0, 255, 0))
        result = self.processor.convert(self.src / "t.png", self.out)
        self.assertTrue(result["converted"])
        with Image.open(self.out / "t.webp") as im:
            self.assertEqual(im.mode, "RGBA")

    def test_la_mode_becomes_rgba(self):
        make_image(self.src / "l.png", mode="LA")
        result = self.processor.convert(self.src / "l.png", self.out)
        self.assertTrue(result["converted"])
        with Image.open(self.out / "l.webp") as im:
            self.assertEqual(im.mode, "RGBA")

    def test_palette_transparent_becomes_rgba(self):
        p = self.src / "p.png"
        img = Image.new("P", (10, 10))
        img.putpalette([0, 0, 0, 255, 255, 255] + [0, 0, 0] * 254)
        img.save(p, transparency=0)
        result = self.processor.convert(p, self.out)
        self.assertTrue(result["converted"])
        with Image.open(self.out / "p.webp") as im:
            self.assertEqual(im.mode, "RGBA")

    def test_resize_when_too_wide(self):
        make_image(self.src / "big.png", size=(3000, 100), mode="RGB")
        result = self.processor.convert(self.src / "big.png", self.out, preset="blog")
        self.assertTrue(result["converted"])
        with Image.open(self.out / "big.webp") as im:
            self.assertLessEqual(im.width, 2000)

    def test_no_resize_when_small(self):
        make_image(self.src / "small.png", size=(100, 100), mode="RGB")
        result = self.processor.convert(self.src / "small.png", self.out, preset="blog")
        self.assertTrue(result["converted"])
        with Image.open(self.out / "small.webp") as im:
            self.assertEqual(im.size, (100, 100))

    def test_exif_orientation_applied(self):
        p = self.src / "rot.jpg"
        img = Image.new("RGB", (100, 50), (10, 20, 30))
        exif = Image.Exif()
        exif[274] = 6  # Rotate 90 CW
        img.save(p, exif=exif)
        result = self.processor.convert(p, self.out)
        self.assertTrue(result["converted"])
        with Image.open(self.out / "rot.webp") as im:
            self.assertEqual(im.size, (50, 100))

    def test_duplicate_conversion_skipped(self):
        make_image(self.src / "d.png", mode="RGB")
        first = self.processor.convert(self.src / "d.png", self.out)
        self.assertTrue(first["converted"])
        second = self.processor.convert(self.src / "d.png", self.out)
        self.assertFalse(second["converted"])
        self.assertTrue(second["skipped"])

    def test_gif_svg_ico_skipped(self):
        for ext in ("gif", "svg", "ico"):
            p = self.src / f"x.{ext}"
            # 这些格式按扩展名直接跳过，处理器不会真正打开，写占位字节即可。
            p.write_bytes(b"dummy")
            result = self.processor.convert(p, self.out)
            self.assertFalse(result["converted"])
            self.assertTrue(result["skipped"])
            self.assertEqual(result["filename"], f"x.{ext}")

    def test_spaces_in_name_replaced(self):
        p = self.src / "my photo.png"
        make_image(p, mode="RGB")
        result = self.processor.convert(p, self.out)
        self.assertEqual(result["filename"], "my_photo.webp")

    def test_same_stem_conflict(self):
        make_image(self.src / "abc.jpg", mode="RGB")
        make_image(self.src / "abc.png", mode="RGB")
        r1 = self.processor.convert(self.src / "abc.jpg", self.out)
        r2 = self.processor.convert(self.src / "abc.png", self.out)
        names = {r1["filename"], r2["filename"]}
        self.assertEqual(names, {"abc.webp", "abc_png.webp"})

    def test_quality_override(self):
        p = make_image(self.src / "q.png", mode="RGB")
        proc = WebPProcessor(quality_overrides={"blog_quality": 50})
        proc.convert(p, self.out, preset="blog")
        self.assertEqual(proc.presets["blog"]["quality"], 50)


class ImageIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vault = self.root / "vault"
        self.project = self.root / "project"
        self.vault.mkdir()
        (self.project / "public/images/blog").mkdir(parents=True)
        (self.project / "public/images/covers").mkdir(parents=True)
        self.config = make_config(self.vault, self.project)
        self.config.ensure_dirs()

    def tearDown(self):
        self.tmp.cleanup()

    def _md(self, name="note.md", content=""):
        path = self.vault / name
        path.write_text(content, encoding="utf-8")
        return path

    def _img(self, rel="Attachments/pic.png", size=(100, 100), mode="RGB"):
        return make_image(self.vault / rel, size=size, mode=mode)

    def test_obsidian_image_to_webp(self):
        self._img()
        md = self._md(content="![[pic.png]]")
        out = image.process_obsidian_images("![[pic.png]]", md, self.config)
        self.assertEqual(out, "![pic.webp](/images/blog/pic.webp)")
        self.assertTrue((self.project / "public/images/blog/pic.webp").exists())

    def test_obsidian_image_with_width(self):
        self._img()
        md = self._md()
        out = image.process_obsidian_images("![[pic.png|668]]", md, self.config)
        self.assertEqual(out, '<img src="/images/blog/pic.webp" alt="pic.webp" width="668">')

    def test_markdown_image_to_webp(self):
        self._img()
        md = self._md()
        out = image.process_markdown_images("![说明](pic.png)", md, self.config)
        self.assertEqual(out, "![说明](/images/blog/pic.webp)")

    def test_html_image_and_caption_preserved(self):
        self._img()
        md = self._md()
        text = '<img src="pic.png" width="680">\n<p class="img-caption">图注</p>'
        out = image.process_html_images(text, md, self.config)
        self.assertIn('<img src="/images/blog/pic.webp"', out)
        self.assertIn('<p class="img-caption">图注</p>', out)

    def test_external_url_not_touched(self):
        md = self._md()
        text = '<img src="https://example.com/pic.png">'
        self.assertEqual(image.process_html_images(text, md, self.config), text)
        text2 = "![x](https://example.com/pic.png)"
        self.assertEqual(image.process_markdown_images(text2, md, self.config), text2)

    def test_cover_converts_to_webp(self):
        self._img("covers_pic.png")
        md = self._md()
        out = cover.process_cover("covers_pic.png", md, self.config)
        self.assertEqual(out, "/images/covers/covers_pic.webp")
        self.assertTrue((self.project / "public/images/covers/covers_pic.webp").exists())

    def test_default_cover_is_webp(self):
        self.assertEqual(cover.DEFAULT_COVER, "/images/covers/default.webp")


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.images = self.root / "public/images"
        (self.images / "blog").mkdir(parents=True)
        (self.images / "covers").mkdir(parents=True)
        self.src = self.root / "src"
        self.src.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_migrate_and_update_references(self):
        make_image(self.images / "blog/a.jpg", mode="RGB")
        make_image(self.images / "covers/c.png", mode="RGB")
        (self.src / "post.md").write_text(
            '![x](/images/blog/a.jpg)\n<img src="public/images/covers/c.png">',
            encoding="utf-8",
        )
        (self.root / "site_config.json").write_text(
            '{"cover": "/images/covers/c.png"}', encoding="utf-8"
        )

        migrator = WebPMigrator(self.root, log=lambda _: None)
        report = migrator.migrate()

        self.assertEqual(report["summary"]["converted"], 2)
        self.assertTrue((self.images / "blog/a.webp").exists())
        self.assertTrue((self.images / "covers/c.webp").exists())

        updated = (self.src / "post.md").read_text(encoding="utf-8")
        self.assertIn("/images/blog/a.webp", updated)
        self.assertIn("public/images/covers/c.webp", updated)

        site = (self.root / "site_config.json").read_text(encoding="utf-8")
        self.assertIn("/images/covers/c.webp", site)

    def test_external_url_not_rewritten(self):
        make_image(self.images / "blog/a.jpg", mode="RGB")
        (self.src / "post.md").write_text(
            '![x](https://example.com/images/blog/a.jpg) ![y](//cdn.example.com/a.jpg)',
            encoding="utf-8",
        )
        migrator = WebPMigrator(self.root, log=lambda _: None)
        migrator.migrate()
        text = (self.src / "post.md").read_text(encoding="utf-8")
        self.assertIn("https://example.com/images/blog/a.jpg", text)
        self.assertIn("//cdn.example.com/a.jpg", text)

    def test_existing_webp_not_duplicated(self):
        # 已有 abc.webp（上次发布的产物）+ 源 abc.jpg，迁移不应再生成 abc_webp.webp。
        make_image(self.images / "blog/abc.jpg", mode="RGB")
        make_image(self.images / "blog/abc.webp", mode="RGB")
        migrator = WebPMigrator(self.root, log=lambda _: None)
        migrator.migrate()
        names = {p.name for p in (self.images / "blog").iterdir()}
        self.assertIn("abc.webp", names)
        self.assertNotIn("abc_webp.webp", names)

    def test_cleanup_deletes_originals_keeps_webp(self):
        make_image(self.images / "blog/a.jpg", mode="RGB")
        migrator = WebPMigrator(self.root, log=lambda _: None)
        migrator.migrate()
        result = migrator.cleanup()
        self.assertEqual(result["count"], 1)
        self.assertFalse((self.images / "blog/a.jpg").exists())
        self.assertTrue((self.images / "blog/a.webp").exists())

    def test_cleanup_skips_when_webp_missing(self):
        make_image(self.images / "blog/a.jpg", mode="RGB")
        migrator = WebPMigrator(self.root, log=lambda _: None)
        migrator.migrate()
        (self.images / "blog/a.webp").unlink()  # 模拟 .webp 缺失
        result = migrator.cleanup()
        self.assertEqual(result["count"], 0)
        self.assertTrue((self.images / "blog/a.jpg").exists())

    def test_gif_untouched(self):
        make_image(self.images / "blog/anim.gif", mode="P")
        migrator = WebPMigrator(self.root, log=lambda _: None)
        report = migrator.migrate()
        self.assertTrue((self.images / "blog/anim.gif").exists())
        self.assertEqual(report["summary"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
