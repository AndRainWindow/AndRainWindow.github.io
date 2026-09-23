# AndRainWindow Publisher Desktop

Tauri 2 + React desktop shell for the existing Python Publisher.

The desktop app does **not** reimplement publishing logic. It launches `python -m publisher.cli` and consumes JSONL events from stdout.

## First run

Requirements:

- Node.js 22+
- Rust stable toolchain
- Python 3.13 (or another supported Python 3 on PATH)
- Existing Publisher Python dependencies (`pip install -r requirements.txt`)
- Windows: WebView2 / Visual Studio C++ build tools required by Tauri

From the repository root:

```powershell
cd desktop
npm install
npm run tauri dev
```

The app reads the repository-root `config.json`. That file remains gitignored, so your local Vault path is not overwritten by `git pull`.

If Python is not available as `python`/`python3`, set:

```powershell
$env:PUBLISHER_PYTHON = "C:\Python313\python.exe"
npm run tauri dev
```

## Current pages

- **Overview** — current paths, WebP status, quick publish
- **Publish** — publish all public notes with live progress
- **Images** — migrate to WebP / cleanup old originals
- **Logs** — live backend logs
- **Settings** — choose Vault/project directories, validate, save config

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
