from pathlib import Path
import json
import math
import re
import shutil
from datetime import datetime


# =========================
# Config
# =========================

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

vault = Path(config["vault"])
output = Path(config["output"])
image_output = Path(config["image_output"])
cover_output = Path(config["cover_output"])

try:
    with open("site_config.json", "r", encoding="utf-8") as f:
        site_config = json.load(f)
except FileNotFoundError:
    site_config = {}

cover_override = site_config.get("cover_override", {})
DEFAULT_COVER = "/images/covers/default.jpg"

output.mkdir(parents=True, exist_ok=True)
image_output.mkdir(parents=True, exist_ok=True)
cover_output.mkdir(parents=True, exist_ok=True)


# =========================
# Helpers
# =========================

def get_field(text, name):
    match = re.search(
        rf"\*\*{re.escape(name)}\*\*[:：](.*)",
        text
    )
    return match.group(1).strip() if match else ""


def safe_name(name):
    return Path(name).name.replace(" ", "_")


def normalize_public_path(path):
    path = str(path).replace("\\", "/").strip()

    if path.startswith("public/"):
        path = "/" + path[len("public/"):]

    if not path.startswith("/"):
        path = "/" + path

    return path


def count_words(text):
    chinese = re.findall(r'[\u4e00-\u9fff]', text)
    english = re.findall(r'[A-Za-z0-9]+', text)
    return len(chinese) + len(english)


def reading_time(word_count):
    return max(1, math.ceil(word_count / 300))


def find_attachment(md_file, filename):
    """
    先找常见位置，找不到就扫描整个 vault。
    """
    filename = Path(filename).name

    paths = [
        md_file.parent / filename,
        md_file.parent / "Attachments" / filename,
        vault / "Attachments" / filename,
    ]

    for parent in md_file.parents:
        paths.append(parent / "Attachments" / filename)

    for path in paths:
        if path.exists() and path.is_file():
            return path

    for path in vault.rglob(filename):
        if ".obsidian" in path.parts or ".trash" in path.parts:
            continue

        if path.is_file():
            return path

    return None


def copy_blog_image(md_file, filename):
    """
    找图并复制到 public/images/blog。
    返回网站 URL；找不到则返回 None。
    """
    filename = Path(filename).name
    source = find_attachment(md_file, filename)

    if not source:
        return None

    new_name = safe_name(filename)

    shutil.copy2(
        source,
        image_output / new_name
    )

    print("Copy image:", new_name)

    return f"/images/blog/{new_name}"


# =========================
# Obsidian wiki image
# =========================

def parse_obsidian_image(raw):
    """
    abc.png
    abc.png|668

    -> filename, width
    """
    parts = raw.split("|", 1)

    filename = parts[0].strip()
    width = None

    if len(parts) > 1:
        option = parts[1].strip()

        if option.isdigit():
            width = option

    return filename, width


def find_first_image(text):
    """
    支持：
    ![[abc.png]]
    ![[abc.png|668]]
    以及已经被旧脚本转换过的 Markdown 图片。
    """

    wiki = re.search(
        r'!\[\[([^\]]+)\]\]',
        text
    )

    if wiki:
        filename, _ = parse_obsidian_image(
            wiki.group(1)
        )
        return filename

    markdown = re.search(
        r'!\[[^\]]*\]\(([^)]+)\)',
        text
    )

    if markdown:
        src = markdown.group(1).strip()

        # 兼容旧脚本生成的 xxx.png|668
        src = re.sub(r'\|\d+$', '', src)

        return Path(src).name

    return None


def process_obsidian_images(text, md_file):
    """
    ![[abc.png]]
    ->
    ![abc.png](/images/blog/abc.png)

    ![[abc.png|668]]
    ->
    <img src="/images/blog/abc.png" alt="abc.png" width="668">
    """

    pattern = re.compile(
        r'!\[\[([^\]]+)\]\]'
    )

    def replace_image(match):
        raw = match.group(1)
        filename, width = parse_obsidian_image(raw)

        url = copy_blog_image(
            md_file,
            filename
        )

        if not url:
            print("Missing image:", filename)

            # 即使找不到，也不要把 |668 留进 URL
            clean_name = safe_name(filename)
            url = f"/images/blog/{clean_name}"

        clean_name = safe_name(filename)

        if width:
            return (
                f'<img src="{url}" '
                f'alt="{clean_name}" '
                f'width="{width}">'
            )

        return (
            f"![{clean_name}]({url})"
        )

    return pattern.sub(
        replace_image,
        text
    )


# =========================
# Repair old broken Markdown
# =========================

def repair_old_markdown_images(text, md_file):
    """
    专门修复旧 publish.py 已经生成出来的这种内容：

    ![abc.png|668](/images/blog/abc.png|668)

    或：

    ![abc.png|668](abc.png|668)

    修复成：

    <img src="/images/blog/abc.png" alt="abc.png" width="668">
    """

    pattern = re.compile(
        r'!\[([^\]]*?)\|(\d+)\]\(([^)]+?)\|(\d+)\)'
    )

    def replace_image(match):
        alt_with_name = match.group(1).strip()
        width = match.group(2)
        raw_src = match.group(3).strip()

        # URL 里去掉旧的 |668
        filename = Path(raw_src).name

        # 如果 Path.name 因 /images/blog/ 正常工作，优先用它；
        # 否则退回 alt 中的文件名。
        if not filename:
            filename = alt_with_name

        clean_name = safe_name(filename)

        source = find_attachment(
            md_file,
            clean_name
        )

        if source:
            shutil.copy2(
                source,
                image_output / clean_name
            )
            print("Repair old image:", clean_name)
        else:
            print("Old image source not found:", clean_name)

        url = f"/images/blog/{clean_name}"

        return (
            f'<img src="{url}" '
            f'alt="{clean_name}" '
            f'width="{width}">'
        )

    return pattern.sub(
        replace_image,
        text
    )


# =========================
# Normal Markdown images
# =========================

def process_markdown_images(text, md_file):
    """
    处理普通 Markdown 相对图片：

    ![说明](abc.jpg)

    已经是 /images/... 或 http(s):// 的不改。
    """

    pattern = re.compile(
        r'!\[([^\]]*)\]\(([^)]+)\)'
    )

    def replace_image(match):
        alt = match.group(1)
        src = match.group(2).strip()

        if (
            src.startswith("/")
            or src.startswith("http://")
            or src.startswith("https://")
            or src.startswith("//")
            or src.startswith("data:")
        ):
            return match.group(0)

        # 防止旧语法残留
        src = re.sub(r'\|\d+$', '', src)

        filename = Path(src).name

        url = copy_blog_image(
            md_file,
            filename
        )

        if not url:
            print("Missing Markdown image:", filename)
            return match.group(0)

        return f"![{alt}]({url})"

    return pattern.sub(
        replace_image,
        text
    )


# =========================
# Raw HTML images
# =========================

def process_html_images(text, md_file):
    """
    <img src="Screenshot.jpg" width="680">

    ->
    <img src="/images/blog/Screenshot.jpg" width="680">

    紧跟在后面的：
    <p class="img-caption">...</p>
    完全保留。
    """

    pattern = re.compile(
        r'(<img\b[^>]*?\bsrc=["\'])([^"\']+)(["\'][^>]*>)',
        re.IGNORECASE
    )

    def replace_image(match):
        prefix = match.group(1)
        src = match.group(2).strip()
        suffix = match.group(3)

        if (
            src.startswith("/")
            or src.startswith("http://")
            or src.startswith("https://")
            or src.startswith("//")
            or src.startswith("data:")
        ):
            return match.group(0)

        filename = Path(src).name

        url = copy_blog_image(
            md_file,
            filename
        )

        if not url:
            print("Missing HTML image:", filename)
            return match.group(0)

        return (
            prefix
            + url
            + suffix
        )

    return pattern.sub(
        replace_image,
        text
    )


# =========================
# Cover
# =========================

def process_cover(image, md_file):
    if not image:
        return DEFAULT_COVER

    # 防止旧格式 xxx.jpg|668
    image = re.sub(r'\|\d+$', '', image)

    source = find_attachment(
        md_file,
        image
    )

    if not source:
        print("Missing cover image:", image)
        return DEFAULT_COVER

    new_name = safe_name(image)

    shutil.copy2(
        source,
        cover_output / new_name
    )

    print("Copy cover:", new_name)

    return f"/images/covers/{new_name}"


def get_cover(title, text, md_file):
    if title in cover_override:
        print("Use custom cover:", title)

        return normalize_public_path(
            cover_override[title]
        )

    image = find_first_image(text)

    if image:
        return process_cover(
            image,
            md_file
        )

    return DEFAULT_COVER


# =========================
# Clean metadata
# =========================

def clean_body(text):
    lines = text.splitlines()

    while lines and not lines[0].strip():
        lines.pop(0)

    metadata = re.compile(
        r'^\s*\*\*(主题|时间|公开|封面)\*\*[:：]'
    )

    while lines:
        line = lines[0].strip()

        if not line:
            lines.pop(0)
            continue

        if metadata.match(line):
            lines.pop(0)
            continue

        if re.fullmatch(
            r'[-—–_\s]{3,}',
            line
        ):
            lines.pop(0)
            continue

        break

    return "\n".join(lines).strip()


# =========================
# Publish
# =========================

for md_file in vault.rglob("*.md"):

    if any(
        folder in md_file.parts
        for folder in [
            "Attachments",
            ".obsidian",
            ".trash"
        ]
    ):
        continue

    try:
        text = md_file.read_text(
            encoding="utf-8"
        )

    except PermissionError:
        print("Skip:", md_file)
        continue

    if get_field(text, "公开") != "是":
        continue

    title = md_file.stem
    date = get_field(text, "时间")
    topics = get_field(text, "主题")

    hero = get_cover(
        title,
        text,
        md_file
    )

    body = text

    # 顺序很重要：
    # 1. 先修旧脚本留下的错误 Markdown
    # 2. 再处理 Obsidian wiki 图片
    # 3. 再处理普通 Markdown 图片
    # 4. 最后处理 HTML 图片
    body = repair_old_markdown_images(
        body,
        md_file
    )

    body = process_obsidian_images(
        body,
        md_file
    )

    body = process_markdown_images(
        body,
        md_file
    )

    body = process_html_images(
        body,
        md_file
    )

    body = clean_body(
        body
    )

    word_count = count_words(body)
    read_minutes = reading_time(word_count)

    modified = datetime.fromtimestamp(
        md_file.stat().st_mtime
    ).strftime("%Y-%m-%d %H:%M:%S")

    title_yaml = json.dumps(
        title,
        ensure_ascii=False
    )

    updated_yaml = json.dumps(
        modified,
        ensure_ascii=False
    )

    topics_yaml = json.dumps(
        topics,
        ensure_ascii=False
    )

    hero_yaml = json.dumps(
        hero,
        ensure_ascii=False
    )

    astro = f"""---
title: {title_yaml}
date: {date}
updated: {updated_yaml}
topics: {topics_yaml}
heroImage: {hero_yaml}
wordCount: {word_count}
readingTime: {read_minutes}
---

{body}
"""

    output_file = output / md_file.name

    output_file.write_text(
        astro,
        encoding="utf-8"
    )

    print("Published:", title)


print("\nFinished.")
