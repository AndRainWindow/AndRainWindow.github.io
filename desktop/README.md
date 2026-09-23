# AndRainWindow Publisher Desktop

Tauri 2 + React desktop shell for the existing Python Publisher.

The desktop app does **not** reimplement publishing logic. It launches `python -m publisher.cli` and consumes JSONL events from stdout.

中文完整使用手册：[`docs/PUBLISHER_USER_GUIDE.md`](../docs/PUBLISHER_USER_GUIDE.md)

## First run

Requirements:

- Python 3.13 (or another supported Python 3 on PATH)
- Existing Publisher Python dependencies (`pip install -r requirements.txt`)
- A local checkout of this website repository, because the desktop shell intentionally reuses its `publisher/` backend

For development you also need:

- Node.js 22+
- Rust stable toolchain
- Tauri platform build dependencies

From the repository root:

```powershell
python -m pip install -r requirements.txt
cd desktop
npm install
npm run tauri dev
```

The app uses the repository-root `config.json`. That file remains local, so Vault paths are not intended to be overwritten by normal source updates.

If Python is not available as `python`/`python3`, set:

```powershell
$env:PUBLISHER_PYTHON = "C:\Python313\python.exe"
npm run tauri dev
```

## Current pages

- **Overview** — paths, WebP status, Python/Publisher readiness, quick publish
- **Publish** — publish all public notes with live progress
- **Images** — migrate to WebP / cleanup old originals
- **Logs** — live backend JSONL and stderr logs
- **Settings** — choose Vault/project directories, validate, save config, re-check Python environment

## Architecture

```text
React UI
  ↓ Tauri invoke/events
Rust bridge
  ↓ child process stdout JSONL
python -m publisher.cli
  ↓
existing Publisher / WebP / migration modules
```

`publisher/cli.py` is the stable bridge contract. Keep business logic in the existing Python modules.

## CI

- Windows: frontend build, Rust check, release build, NSIS installer artifact
- Linux: frontend build + Rust compile check
- macOS: frontend build + Rust compile check
