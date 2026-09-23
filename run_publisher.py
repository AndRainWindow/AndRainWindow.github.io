#!/usr/bin/env python3
"""AndRainWindow Publisher 统一入口。

用法：
    python run_publisher.py           # 命令行发布
    python run_publisher.py --gui     # 启动图形界面
"""

from publisher.app import main

if __name__ == "__main__":
    raise SystemExit(main())
