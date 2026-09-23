"""Tkinter 图形界面。

发布操作跑在 worker 线程里，通过 queue.Queue 回传进度与日志，
GUI 用 root.after(...) 轮询队列，避免界面卡死。
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from ..config import PublisherConfig, build_config, load_config, save_config
from ..publisher import Publisher, PublishResult


class PublisherGUI(tk.Tk):
    def __init__(self, config_path: str | Path, site_config_path: str | Path):
        super().__init__()

        self.config_path = Path(config_path)
        self.site_config_path = Path(site_config_path)

        self.queue: queue.Queue = queue.Queue()
        self.cover_override: dict[str, str] = {}
        self.running = False

        self._preload_cover_override()

        self.title("AndRainWindow Publisher")
        self.geometry("720x600")
        self.minsize(560, 480)

        self.vault_var = tk.StringVar()
        self.project_var = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪")
        self.percent_var = tk.StringVar(value="0%")
        self.webp_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._load_initial_paths()

        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def _preload_cover_override(self) -> None:
        try:
            config = load_config(self.config_path, self.site_config_path)
            self.cover_override = dict(config.cover_override)
        except Exception:
            self.cover_override = {}

    def _load_initial_paths(self) -> None:
        try:
            config = load_config(self.config_path, self.site_config_path)
            self.vault_var.set(str(config.vault))
            self.project_var.set(str(config.project))
            self.webp_var.set(config.webp_enabled)
        except Exception:
            # 配置缺失时留空，等用户手动选择。
            pass

    # ------------------------------------------------------------------
    # 界面构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        padding = {"padx": 16, "pady": 6}

        header = ttk.Label(
            self,
            text="AndRainWindow Publisher",
            font=("", 16, "bold"),
        )
        header.pack(anchor="w", **padding)

        form = ttk.Frame(self)
        form.pack(fill="x", **padding)

        # Obsidian Vault
        ttk.Label(form, text="Obsidian Vault").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.vault_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(form, text="浏览…", command=self._browse_vault).grid(row=0, column=2)

        # Astro Project
        ttk.Label(form, text="Astro Project").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(form, textvariable=self.project_var).grid(row=1, column=1, sticky="ew", padx=8, pady=(10, 0))
        ttk.Button(form, text="浏览…", command=self._browse_project).grid(row=1, column=2, pady=(10, 0))

        form.columnconfigure(1, weight=1)

        self.webp_check = ttk.Checkbutton(
            self,
            text="启用 WebP 图片压缩",
            variable=self.webp_var,
        )
        self.webp_check.pack(anchor="w", **padding)

        actions = ttk.Frame(self)
        actions.pack(anchor="w", **padding)
        self.publish_btn = ttk.Button(actions, text="开始发布", command=self._start_publish)
        self.publish_btn.pack(side="left")
        self.migrate_btn = ttk.Button(actions, text="迁移现有图片", command=self._start_migrate)
        self.migrate_btn.pack(side="left", padx=(8, 0))

        # 进度条
        progress_row = ttk.Frame(self)
        progress_row.pack(fill="x", **padding)

        self.progress = ttk.Progressbar(progress_row, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True)

        ttk.Label(progress_row, textvariable=self.percent_var, width=6).pack(side="right", padx=(8, 0))

        # 当前正在处理的文章
        ttk.Label(self, textvariable=self.status_var).pack(anchor="w", **padding)

        # 日志窗口
        self.log_text = scrolledtext.ScrolledText(self, height=16, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    # ------------------------------------------------------------------
    # 路径选择
    # ------------------------------------------------------------------

    def _browse_vault(self) -> None:
        path = filedialog.askdirectory(title="选择 Obsidian Vault")
        if path:
            self.vault_var.set(path)

    def _browse_project(self) -> None:
        path = filedialog.askdirectory(title="选择 Astro 项目目录")
        if path:
            self.project_var.set(path)

    # ------------------------------------------------------------------
    # 发布
    # ------------------------------------------------------------------

    def _start_publish(self) -> None:
        if self.running:
            return

        vault = self.vault_var.get().strip()
        project = self.project_var.get().strip()

        if not vault or not project:
            messagebox.showwarning("缺少路径", "请先选择 Obsidian Vault 和 Astro 项目目录。")
            return

        config = build_config(vault, project, self.cover_override)
        config.webp["enabled"] = self.webp_var.get()

        problems = config.validate()
        if problems:
            messagebox.showerror("路径错误", "\n".join(problems))
            return

        # 自动保存路径
        save_config(config, self.config_path)

        self._reset_ui()
        self.running = True
        self.publish_btn.config(state="disabled")

        threading.Thread(target=self._worker, args=(config,), daemon=True).start()

    def _reset_ui(self) -> None:
        self.progress.config(maximum=100, value=0)
        self.percent_var.set("0%")
        self.status_var.set("准备中…")
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _worker(self, config: PublisherConfig) -> None:
        def on_progress(current: int, total: int) -> None:
            self.queue.put(("progress", current, total))

        def on_log(msg: str) -> None:
            self.queue.put(("log", msg))

        def on_file(filename: str) -> None:
            self.queue.put(("file", filename))

        publisher = Publisher(
            config,
            on_progress=on_progress,
            on_log=on_log,
            on_file=on_file,
        )

        try:
            result = publisher.publish_all()
            self.queue.put(("done", result))
        except Exception as exc:
            self.queue.put(("error", str(exc)))

    def _start_migrate(self) -> None:
        if self.running:
            return

        project = self.project_var.get().strip()

        if not project:
            messagebox.showwarning("缺少路径", "请先选择 Astro 项目目录。")
            return

        config = build_config(self.vault_var.get().strip(), project, self.cover_override)
        quality_overrides = config.webp_quality_overrides()

        self._reset_ui()
        self.running = True
        self.publish_btn.config(state="disabled")
        self.migrate_btn.config(state="disabled")
        self.status_var.set("正在迁移图片…")

        threading.Thread(target=self._migrate_worker, args=(project, quality_overrides), daemon=True).start()

    def _migrate_worker(self, project: str, quality_overrides: dict) -> None:
        def on_log(msg: str) -> None:
            self.queue.put(("log", msg))

        try:
            from ..migration.webp_migrator import WebPMigrator

            migrator = WebPMigrator(project, quality_overrides=quality_overrides, log=on_log)
            report = migrator.migrate()
            self.queue.put(("migrate_done", report))
        except Exception as exc:
            self.queue.put(("error", str(exc)))

    # ------------------------------------------------------------------
    # 队列轮询
    # ------------------------------------------------------------------

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, *payload = self.queue.get_nowait()

                if kind == "progress":
                    current, total = payload
                    pct = int(current / total * 100) if total else 100
                    self.progress.config(maximum=total, value=current)
                    self.percent_var.set(f"{pct}%")
                elif kind == "file":
                    self.status_var.set(f"当前：{payload[0]}")
                elif kind == "log":
                    self._append_log(payload[0])
                elif kind == "done":
                    self._on_done(payload[0])
                elif kind == "migrate_done":
                    self._on_migrate_done(payload[0])
                elif kind == "error":
                    self._on_error(payload[0])
        except queue.Empty:
            pass

        self.after(100, self._poll_queue)

    def _append_log(self, msg: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _on_done(self, result: PublishResult) -> None:
        self.running = False
        self.publish_btn.config(state="normal")
        self.status_var.set("完成")

        if result.failures:
            details = "\n".join(f"{name}: {reason}" for name, reason in result.failures)
            messagebox.showwarning(
                "发布完成（有失败）",
                f"{result.summary()}\n\n失败明细：\n{details}",
            )
        else:
            messagebox.showinfo("发布完成", result.summary())

    def _on_migrate_done(self, report: dict) -> None:
        self.running = False
        self.publish_btn.config(state="normal")
        self.migrate_btn.config(state="normal")
        self.status_var.set("迁移完成")

        s = report["summary"]
        messagebox.showinfo(
            "迁移完成",
            f"转换 {s['converted']} 张，跳过 {s['skipped']} 张，"
            f"更新引用 {s['references_updated_files']} 个文件。\n\n"
            "确认 npm run build 成功后，运行\n"
            "python run_publisher.py --cleanup\n"
            "删除被 .webp 替代的原图。",
        )

    def _on_error(self, message: str) -> None:
        self.running = False
        self.publish_btn.config(state="normal")
        self.migrate_btn.config(state="normal")
        self.status_var.set("出错")
        messagebox.showerror("发布出错", message)


def launch_gui(config_path: str | Path, site_config_path: str | Path) -> int:
    """启动 GUI，返回退出码。"""
    app = PublisherGUI(config_path, site_config_path)
    app.mainloop()
    return 0
