# AndRainWindow Publisher 使用手册

## v0.2.0 摄影管理

更新桌面程序后，也需要在网站项目目录执行 `git pull`，让本地 Python 后端与桌面版保持一致。安装包不内置 Python。

### 导入与分组

1. 在 Settings 选择网站项目并保存。摄影管理不需要 Obsidian Vault。
2. 进入“摄影管理”，点击“选择一组照片”，每次最多选择 200 张 JPG/JPEG（也兼容 PNG/WebP）。
3. 程序读取 EXIF 拍摄时间、相机、镜头、ISO、光圈、快门和焦距。缺少日期时，使用“缺失拍摄日期时补填”或单张编辑器填写；不会使用文件修改日期冒充拍摄时间。
4. 填写整组标题、感受。组内单张标题和感受默认留空，避免网页反复展示相同文字。可逐张补充独立内容。
5. 点击“保存整组到本地”。原 JPG 保留在来源目录，网站目录中只新增 WebP；相同文件内容重复导入会跳过。

网站保持当前三栏布局。按拍摄时间排序后，第一张可见照片显示组标题和感受，单张填写的内容优先。首张隐藏／删除后，下一张可见照片承接组信息。左边继续显示年月日，右边仅显示 HH:mm，不做电脑时区换算。旧照片只有日期时右边时间留空。

### 历史作品管理

照片库可以按标题、地点、日期搜索，筛选隐藏照片或回收站。点击单张修改其信息，点击“整组”修改组标题与感受。单张隐藏和整组隐藏独立保存；恢复整组不会抹去之前的单张隐藏状态。删除先进入回收站，可以恢复，不会删除原 JPG。

### 本地预览，再上线

本地预览需安装 Node.js 22.12+，并在网站仓库运行一次 `npm install`。

1. 保存所有照片修改。
2. 点击“生成本地预览”：执行网站构建，通过后在浏览器打开本机地址。
3. 检查图片、标题、感受、时间和地点。
4. 点击“确认并提交上线”：提交照片信息和被引用的 WebP，再推送到 origin/main，随后由 GitHub Pages 部署。

预览后改动照片，需要重新预览。程序不会提交其他文件或原 JPG。Git 需要事先登录、配置用户名／邮箱，并使用跟踪 origin/main 的 main 分支。如果有其他未提交文件、暂存内容或未同步提交，先在终端处理后再预览；不会自动合并或强推。网络导致推送失败时可重试，不会重复创建同一提交。

本机预览只监听 127.0.0.1，关闭程序或一小时后停止。预览期间保存到本地的内容尚未上线。

### GPS 自动识别区县

摄影页底部可以保存自己的 Geoapify API Key。配置后导入含 GPS 的照片会自动查城市和区县，结果缓存于本机；也可对选中照片单独查询。识别不到区县时会提示补填。没有 GPS、未配置密钥或断网不阻止导入与发布。

API Key、原图路径和原始坐标存于 `.publisher-local/`，该目录被 Git 忽略；查询时只向 Geoapify 发送坐标。照片 JSON 和 WebP 不包含原始 GPS。摄影页仅展示地区名称，可手动修正。服务文档：https://apidocs.geoapify.com/docs/geocoding/reverse-geocoding/

### 验证路径

点击“验证路径”后，Settings 页会就地显示“验证中”、通过提示或具体错误；修改路径后旧结果清除。该按钮检查目录，保存配置后下方 Python 环境检查负责检查解释器及依赖。仅做摄影时可留空 Vault；博客发布仍需要有效 Vault。

> 适用于当前的 Tauri 2 + React 桌面版 Publisher。
>
> 桌面程序是现有 Python Publisher 的图形控制台：它不会复制或重写发布逻辑，而是调用本地项目中的 `python -m publisher.cli`。

## 1. 这套工具是做什么的

完整流程：

```text
Obsidian Vault
    ↓
Python Publisher
    ├─ 读取“公开”笔记
    ├─ 处理图片 / WebP
    ├─ 生成封面与统计信息
    └─ 输出 Markdown
    ↓
Astro src/content/blog + public/images
    ↓
Git / GitHub Pages
```

桌面 GUI 负责：

- 选择 Obsidian Vault 和 Astro 项目目录；
- 检查 Python / Pillow / Publisher 环境；
- 一键发布全部公开笔记；
- 执行 WebP 迁移和旧原图清理；
- 显示进度、当前文件、结果和实时日志；
- 调用现有 Python 后端，不在 Rust/React 中重复实现业务逻辑。

## 2. Windows 最快上手

### 2.1 准备本地项目

桌面程序目前不会把 Python Publisher 打进安装包，所以电脑上仍需要保留本网站仓库，例如：

```text
E:\Documents\D_Dev\Active\PersonelWebsite
```

这个目录至少应包含：

```text
package.json
publisher/
  cli.py
config.json          # 首次保存设置后使用
site_config.json
requirements.txt
```

### 2.2 安装 Python 依赖

推荐 Python 3.13。进入项目根目录：

```powershell
cd E:\Documents\D_Dev\Active\PersonelWebsite
python -m pip install -r requirements.txt
```

当前 Python 依赖至少包含 Pillow。

确认：

```powershell
python -c "import publisher; from PIL import Image; print('OK')"
```

看到 `OK` 即可。

如果系统中的 Python 命令不是 `python`，可以设置环境变量：

```powershell
$env:PUBLISHER_PYTHON = "C:\Python313\python.exe"
```

长期使用时可在 Windows 系统环境变量中创建同名变量。

### 2.3 安装桌面程序

GitHub Actions 的 `Desktop GUI CI` 会生成 Windows artifact：

```text
AndRainWindow-Publisher-Windows
```

其中通常包含：

```text
andrainwindow-publisher.exe
AndRainWindow Publisher_0.1.0_x64-setup.exe
```

日常使用优先安装 `...setup.exe`。

### 2.4 第一次配置

打开程序后进入 **Settings**：

1. `Obsidian Vault` 选择你的 Vault，例如：
   `E:\obsidian\AndRainWindow`
2. `Astro Project` 选择网站项目，例如：
   `E:\Documents\D_Dev\Active\PersonelWebsite`
3. 点击 **验证路径**。
4. 没有错误后点击 **保存配置**。
5. 查看下面的 **Python Publisher** 环境卡片。

正常状态应显示：

```text
Ready
Executable        python / C:\...\python.exe
Version           Python 3.x.x
Publisher + Pillow Available
```

完成后 Overview 页面中的 Python 卡片也会显示 Ready。

## 3. 每个页面怎么用

### Overview

总览页显示：

- Vault 目录；
- Astro Project 目录；
- WebP 是否开启；
- Python / Publisher 环境状态；
- Quick publish；
- 当前任务状态和进度。

如果环境未就绪，发布按钮会禁用，并提示去 Settings 检查。

### Publish

点击 **开始发布** 后会执行：

```bash
python -m publisher.cli publish
```

发布器会扫描 Vault 中的 Markdown，只发布：

```md
**公开**：是
```

单篇失败不会使整个批次立即停止。完成后界面会显示：

```text
成功 N · 失败 N · 跳过 N
```

### Images

这里有两个操作。

#### 迁移到 WebP

用于把已有 `public/images` 中的站点图片迁移到 WebP，并更新本地引用。

迁移阶段默认保留原图，因此适合先运行、检查和构建验证。

推荐流程：

```text
迁移到 WebP
→ 检查页面
→ npm run build
→ 确认图片正常
→ 再考虑清理旧原图
```

#### 清理旧原图

这是破坏性操作。它会删除已经被 WebP 替代、且迁移器认为可以清理的旧图片。

只有在以下条件都满足时再执行：

- WebP 迁移完成；
- Astro 本地预览正常；
- `npm run build` 成功；
- Git 中没有异常引用变化；
- 重要原图另有备份，或仍保存在 Obsidian Vault / 相册中。

程序执行前还会再次要求确认。

### Logs

显示 Python CLI 输出的实时 JSONL 事件和 stderr 日志。

如果发布失败，优先到这里查：

- 缺图；
- 路径错误；
- Python 依赖缺失；
- 文件转换失败；
- 某一篇 Markdown 处理异常。

### Settings

这里维护两类信息：

- Publisher 配置：Vault、项目目录、WebP 开关；
- Python 运行环境状态。

`config.json` 仍然是 Python Publisher 和桌面 GUI 的共同配置源。

桌面程序还会单独记住“项目目录在哪里”，用于安装版程序下次启动时重新找到 `config.json`。

项目指针保存位置：

```text
Windows:
%APPDATA%\AndRainWindow\Publisher\state.json

macOS:
~/Library/Application Support/AndRainWindow/Publisher/state.json

Linux:
$XDG_CONFIG_HOME/andrainwindow-publisher/state.json
或 ~/.config/andrainwindow-publisher/state.json
```

## 4. Obsidian 笔记格式

Publisher 支持顶部元数据：

```md
**主题**：Android, ADB
**时间**：2026-09-14
**公开**：是
**封面**：可选
---

正文……
```

冒号 `:` 和全角冒号 `：` 都支持。

只有 `**公开**：是` 会被发布；其他笔记会跳过。

正文不需要迁移成 YAML frontmatter。Publisher 会负责生成 Astro 需要的输出格式。

## 5. 图片规则

站点公共图片放在：

```text
public/images/...
```

网页 URL 写成：

```text
/images/...
```

不要写：

```text
/public/images/...
```

来自 `public` 的运行时图片路径应使用普通 `<img>`，不要把 `/images/...` 字符串直接交给 `astro:assets` 的 `<Image>`。

Publisher 当前可处理常见 Obsidian / Markdown 图片写法，并将需要发布的位图复制或转换到站点图片目录。

## 6. 推荐日常工作流

写博客时：

```text
1. 在 Obsidian 写笔记
2. 确认元数据
3. 最后设置 **公开**：是
4. 打开 AndRainWindow Publisher
5. Overview → Quick publish
6. 看结果；失败时看 Logs
7. 本地 Astro 检查（需要时）
8. Git commit / push
9. GitHub Pages 自动部署
```

如果只是改了未公开笔记，可以不运行 Publisher。

## 7. 命令行备用方案

GUI 出问题时，所有核心操作仍可直接从项目根目录执行。

### 检查配置

```powershell
python -m publisher.cli config
```

### 验证路径

```powershell
python -m publisher.cli validate
```

### 发布

```powershell
python -m publisher.cli publish
```

### WebP 迁移

```powershell
python -m publisher.cli migrate-webp
```

### 清理旧原图

```powershell
python -m publisher.cli cleanup-webp
```

CLI 使用 JSON Lines 输出，桌面程序就是读取这些事件来显示进度和日志。

## 8. 常见问题

### Python not found

确认：

```powershell
python --version
```

如果 Python 安装在固定路径但没有加入 PATH：

```powershell
$env:PUBLISHER_PYTHON = "C:\Python313\python.exe"
```

然后重新打开桌面程序。

### Python 可用，但 Publisher/Pillow 未通过

在网站项目目录执行：

```powershell
python -m pip install -r requirements.txt
python -c "import publisher; from PIL import Image; print('OK')"
```

另外确认 Settings 中的 Astro Project 指向真正的网站根目录，而不是 `desktop` 子目录。

### 项目目录无效

正确目录必须同时包含：

```text
package.json
publisher/cli.py
```

所以应该选择：

```text
PersonelWebsite
```

而不是：

```text
PersonelWebsite\desktop
```

### 发布按钮是灰色

说明环境检查尚未通过。进入 Settings 查看 Python Publisher 卡片并点击 **重新检查**。

### 发布后网页没有变化

依次检查：

1. 笔记是否为 `**公开**：是`；
2. `src/content/blog` 是否生成或更新文件；
3. Astro 是否读取正确 collection；
4. 是否完成 Git commit / push；
5. GitHub Pages workflow 是否成功。

### 图片找不到

查看 Logs 中的具体原始文件名，再确认附件是否位于：

- 笔记同目录；
- 笔记目录的 `Attachments`；
- Vault 的 `Attachments`；
- 上级目录的 `Attachments`。

Publisher 最后还会在 Vault 中进行更广的查找。

## 9. 开发桌面 GUI

首次开发需要 Node.js、Rust、Python 和对应平台的 Tauri 系统依赖。

从项目根目录：

```powershell
cd desktop
npm install
npm run tauri dev
```

只构建 React：

```powershell
npm run build
```

检查 Rust bridge：

```powershell
cargo check --manifest-path src-tauri/Cargo.toml
```

Windows release：

```powershell
npm run tauri build -- --bundles nsis
```

生成文件位于：

```text
src-tauri/target/release/
src-tauri/target/release/bundle/nsis/
```

## 10. 当前跨平台状态

CI 会进行：

```text
Windows  React build + Rust check + NSIS release build
Linux    React build + Rust compile check
macOS    React build + Rust compile check
```

目前正式自动打包的是 Windows。macOS/Linux 先用于持续编译验证，后续如需要发布给其他机器，再单独增加 `.dmg` / `.AppImage` 等 release artifact。

## 11. 更新程序与项目

网站项目更新：

```powershell
git pull
python -m pip install -r requirements.txt
```

如果桌面 GUI 有新版本，可从最新成功的 `Desktop GUI CI` 下载新的 Windows artifact 并重新安装。

正常情况下，更新桌面程序不会修改你的 Obsidian Vault；Publisher 只读取公开笔记并向 Astro 项目输出内容。
