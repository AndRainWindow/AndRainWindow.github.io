"""字数与阅读时间统计。

- 中文：按字符计数
- 英文：按单词计数
- 阅读速度：300 字/分钟
"""

from __future__ import annotations

import math
import re


def count_words(text: str) -> int:
    chinese = re.findall(r"[一-鿿]", text)
    english = re.findall(r"[A-Za-z0-9]+", text)
    return len(chinese) + len(english)


def reading_time(word_count: int) -> int:
    return max(1, math.ceil(word_count / 300))
