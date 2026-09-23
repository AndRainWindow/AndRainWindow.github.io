# AndRainWindow Publisher

把 Obsidian Vault 中标记为「公开」的笔记，发布成 Astro 博客内容（Markdown + 图片），图片统一转成 WebP。

```
Obsidian Vault ──► Publisher ──► src/content/blog/ + public/images/（WebP）
```

## 如何启动

```sh
# 命令行发布
python run_publisher.py

# 图形界面
python run_publisher.py --gui

# 一次性迁移现有图片到 WebP（含引用更新）
python run_publisher.py --migrate

# npm run build 成功后，删除被 .webp 替代的原图
python run_publisher.py --cleanup
```

GUI 里只需选择两个路径，输出目录会自动推导：

- `Obsidian Vault` → 例如 `E:\obsidian\AndRainWindow`
- `Astro Project` → 例如 `E:\Documents\D_Dev\Active\PersonelWebsite`

派生出的输出目录：

| 输出 | 路径 |
|------|------|
| 文章 | `Astro/src/content/blog` |
| 正文图片 | `Astro/public/images/blog` |
| 封面 | `Astro/public/images/covers` |

## 目录结构

```
publisher/
├── config.py           配置加载与保存（唯一读 JSON 的地方）
├── publisher.py        Publisher 核心调度器
├── app.py              CLI 入口编排
├── parsers/
│   ├── metadata.py     解析 **主题** / **时间** / **公开** / **封面**
│   └── images.py       识别各类图片语法（纯解析，不复制文件）
├── processors/
│   ├── webp.py         WebP 转换（格式/缩放/透明/EXIF/重复检测）
│   ├── image.py        查找附件、复制/转 WebP、生成 URL、修正旧错误路径
│   ├── cover.py        封面优先级：cover_override → 首图 → default.webp
│   ├── stats.py        字数、阅读时间
│   └── article.py      完整文章转换流程
├── migration/
│   └── webp_migrator.py  一次性迁移工具（Phase A 迁移 / Phase B 清理）
└── gui/
    └── main_window.py  Tkinter 界面（仅界面 + 线程调度）

run_publisher.py        统一入口
config.json             本地配置（vault + project + webp）
site_config.json        封面手动覆盖等站点配置
```

## 配置方式

`config.json`（本地，不入库）：

```json
{
    "vault": "E:/obsidian/AndRainWindow",
    "project": "E:/Documents/D_Dev/Active/PersonelWebsite",
    "webp": {
        "enabled": true
    }
}
```

- `webp.enabled`：是否把图片转成 WebP（默认开）。
- 可选质量覆盖：`"webp": { "blog_quality": 75, "cover_quality": 70 }`，不加则用内置预设。

`site_config.json`（可选，手动指定封面）：

```json
{
    "cover_override": {
        "某篇文章标题": "/images/covers/xxx.jpg"
    }
}
```

## 发布流程

1. 扫描 Vault 下所有 `.md`（跳过 `Attachments` / `.obsidian` / `.trash`）。
2. 只发布 `**公开**：是` 的笔记；其余记为「跳过」。
3. 单篇失败不会中断整个发布，会记录错误并继续下一篇。
4. 结束后汇总：`成功 / 失败 / 跳过`。

## 支持的图片语法

PNG / JPG / JPEG / WEBP 会转成 `.webp`（透明 PNG 保留 alpha，EXIF 方向自动修正，超宽自动缩放）；GIF / SVG / ICO 保持原样。

| 输入 | 输出（WebP 开启时） |
|------|------|
| `![[abc.png]]` | `![abc.webp](/images/blog/abc.webp)` |
| `![[abc.png\|668]]` | `<img src="/images/blog/abc.webp" alt="abc.webp" width="668">` |
| `![alt](abc.png)` | `![alt](/images/blog/abc.webp)` |
| `<img src="abc.jpg" width="680">` | `<img src="/images/blog/abc.webp" width="680">` |
| 旧错误 `![abc.png\|668](/images/blog/abc.png\|668)` | 自动修复成上面的 `<img>` |

同名冲突（`abc.jpg` 与 `abc.png` 都要输出 `abc.webp`）时，第二个会得到 `abc_png.webp`。

不会生成 `/images/blog/xxx.jpg|668` 或 `/blog/文章名/xxx.jpg` 这类错误路径；外链 `http(s)://`、`//` 一律不改。

### WebP 预设

| 目录 | 最大宽度 | 质量 |
|------|---------|------|
| `blog` | 2000 | 82 |
| `cover` | 1600 | 80 |
| `photo` | 2560 | 85 |
| `hero` | 2560 | 82 |

## 一次性迁移现有图片

仓库里已有的 `public/images` 图片可以用 `--migrate` 一次性转成 WebP：

1. `python run_publisher.py --migrate`
   - 扫描 `public/images`，按目录选预设转换；
   - 更新 `src/` 与 `site_config.json` 里 `/images/...` 和 `public/images/...` 引用（外链不动）；
   - 生成 `migration_report.json`。
2. `npm run build`，确认构建成功、无 404。
3. `python run_publisher.py --cleanup`
   - 按报告删除被 `.webp` 替代的原图（缺 `.webp` 的不删）。

## 扩展点

以后要加 Git 自动提交、摄影管理等功能，可以新增独立的 processor / service，接进 `article.py` 的转换流水线或 `publisher.py` 的调度流程，不必再改一个几百行的单文件脚本。
