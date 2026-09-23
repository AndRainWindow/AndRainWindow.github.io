# AndRainWindow Publisher v0.2.0

本版本加入完整摄影管理，并修复 Settings 中“验证路径”缺少成功反馈和错误提示的问题。

## 安装与更新

1. Windows x64 下载 `*-setup.exe` 安装。
2. 在本地网站仓库运行 `git pull`，然后 `python -m pip install -r requirements.txt`。
3. 使用 Python 3.11+（推荐 3.13）；本程序仍调用系统 Python，不使用 PyInstaller。
4. 本地预览另需 Node.js 22.12+，在网站仓库运行一次 `npm install`。
5. 提交上线需要本机 Git 已登录 GitHub，且当前分支为跟踪 `origin/main` 的 `main`。

## 摄影工作流

- 选择一组 JPG/JPEG → 读取 EXIF → 填写组标题和感受 → 保存为 WebP。
- JPG 原图不复制到网站，也不上传；WebP 修正方向、限制宽度、保留 ICC 色彩配置。
- 自动读取相机、镜头、ISO、光圈、快门、焦距、拍摄日期与分钟。
- 摄影页保持原布局：左侧年月日不变；右侧只显示 `HH:mm`。
- 组标题和感受只在第一张可见照片展示；单张可单独填写、修改。
- 支持单张／整组隐藏、恢复、移入回收站及恢复。回收站不删除原图。
- 保存本地后，先生成预览；检查后点击“确认并提交上线”。仅提交照片目录中被引用的 WebP 及照片信息。
- 原始 GPS、原图路径及密钥仅保存在被 Git 忽略的 `.publisher-local/` 中。

## 可选 GPS 区县识别

在摄影页底部填写自己的 Geoapify API Key 后，导入含 GPS 的照片会自动查询城市和区县，并缓存结果。旧照片可点击“GPS 识别区县”。查询服务只接收坐标，不接收 JPG；结果允许修改。

没有坐标、没有配置密钥或地图查询失败时，仍可以手动填写地点并发布。区县覆盖取决于服务数据，不会把街道或门牌当作区县输出。

Geoapify 说明：https://apidocs.geoapify.com/docs/geocoding/reverse-geocoding/

## 说明

- 旧照片只有日期时不会伪造 `00:00`；重新导入含 EXIF 的 JPG 或编辑时间可以补全。
- GUI 仅控制当前电脑上的网站仓库。网站隐藏不构成文件访问保护；公开仓库内的 WebP 仍可能通过直接链接访问。
- 若仓库有其他未提交修改、未同步提交或已有暂存内容，程序会提示先处理，不会自动合并、强推或替你提交其他工作。
- 校验文件见 `SHA256SUMS.txt`。Windows 安装包与 Linux/macOS 编译检查由 GitHub Actions 生成。
