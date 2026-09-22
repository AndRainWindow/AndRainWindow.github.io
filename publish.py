from pathlib import Path
import json
import re
import shutil
from datetime import datetime
import math

# Config
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

vault = Path(config["vault"])
output = Path(config["output"])
image_output = Path(config["image_output"])
cover_output = Path(config["cover_output"])


# Site config
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


def get_field(text, name):
    match = re.search(
        rf"\*\*{name}\*\*[:：](.*)",
        text
    )
    return match.group(1).strip() if match else ""


def find_attachment(md_file, filename):
    paths = [
        md_file.parent / "Attachments" / filename,
        vault / "Attachments" / filename,
    ]

    for parent in md_file.parents:
        paths.append(parent / "Attachments" / filename)

    for path in paths:
        if path.exists():
            return path

    return None

def count_words(text):
    # 中文按单字计算
    chinese = re.findall(r'[\u4e00-\u9fff]', text)

    # 英文/数字按单词计算
    english = re.findall(r'[A-Za-z0-9]+', text)

    return len(chinese) + len(english)


def reading_time(word_count):
    return max(1, math.ceil(word_count / 300))

def safe_name(name):
    return name.replace(" ", "_")


def find_first_image(text):
    images = re.findall(
        r'!\[\[(.*?)\]\]',
        text
    )

    return images[0] if images else None


def process_images(text, md_file):
    images = re.findall(
        r'!\[\[(.*?)\]\]',
        text
    )

    for image in images:
        source = find_attachment(
            md_file,
            image
        )

        new_name = safe_name(image)

        if source:
            shutil.copy2(
                source,
                image_output / new_name
            )
            print("Copy image:", new_name)

        else:
            print("Missing image:", image)

        text = text.replace(
            f"![[{image}]]",
            f"![{new_name}](/images/blog/{new_name})"
        )

    return text


def process_cover(image, md_file):
    if not image:
        return DEFAULT_COVER

    source = find_attachment(
        md_file,
        image
    )

    if not source:
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
        return cover_override[title]

    image = find_first_image(text)

    if image:
        return process_cover(
            image,
            md_file
        )

    return DEFAULT_COVER


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

        # 删除顶部各种横线分隔符
        if re.fullmatch(r'[-—–_\s]{3,}', line):
            lines.pop(0)
            continue

        break

    return "\n".join(lines).strip()


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

    body = process_images(
        text,
        md_file
    )

    body = clean_body(body)

    word_count = count_words(body)

    read_minutes = reading_time(
        word_count
    )

    modified = datetime.fromtimestamp(
        md_file.stat().st_mtime
    ).strftime("%Y-%m-%d %H:%M:%S")

    astro = f"""---
title: "{title}"
date: {date}
updated: "{modified}"
topics: "{topics}"
heroImage: "{hero}"
wordCount: {word_count}
readingTime: {read_minutes}
---

{body}
"""


    (output / md_file.name).write_text(
        astro,
        encoding="utf-8"
    )

    print("Published:", title)


print("\nFinished.")