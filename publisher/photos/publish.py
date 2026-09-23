"""Build/preview first, then commit and push ONLY reviewed photo changes."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
import threading
import uuid
from pathlib import Path

from .catalog import atomic_json, read_json


def run(root, args, timeout=120):
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'}
    try:
        result = subprocess.run(args, cwd=root, env=env, capture_output=True,
                                timeout=timeout, encoding='utf-8', errors='replace')
    except FileNotFoundError:
        raise ValueError(f'找不到 {args[0]}，请安装并加入 PATH。') from None
    except subprocess.TimeoutExpired:
        raise ValueError('操作超时；请检查网络或在终端完成登录后重试。') from None
    if result.returncode:
        raise ValueError((result.stderr or result.stdout or '命令执行失败')[-4000:])
    return result.stdout.strip()


def git(root, *args):
    return run(root, ['git', *args])


def changed_files(root):
    # -z preserves spaces, Unicode and newline-containing file names.
    output = git(root, 'ls-files', '--modified', '--deleted', '--others', '--exclude-standard', '-z')
    return sorted(set(p for p in output.split('\0') if p))


def allowed(catalog):
    paths = {'src/data/photos.json'}
    for photo in catalog.load():
        image = photo.get('image', '')
        if image.startswith('/images/photos/') and image.endswith('.webp'):
            candidate = (catalog.root / 'public' / image.lstrip('/')).resolve()
            if candidate.is_relative_to(catalog.output.resolve()):
                paths.add(candidate.relative_to(catalog.root).as_posix())
    return paths


def fingerprint(catalog):
    # The exact photo files reviewed, including retained hidden/trash images.
    digest = hashlib.sha256()
    for name in sorted(allowed(catalog)):
        path = catalog.root / name
        digest.update(name.encode())
        if not path.is_file():
            raise ValueError(f'照片文件缺失：{name}')
        digest.update(path.read_bytes())
    return digest.hexdigest()


def validate_worktree(catalog):
    root = catalog.root
    if git(root, 'diff', '--cached', '--name-only'):
        raise ValueError('Git 暂存区已有其他操作，请先提交或取消暂存后再用 GUI 发布。')
    changed = changed_files(root)
    unexpected = [p for p in changed if p not in allowed(catalog)]
    if unexpected:
        raise ValueError('请先处理照片以外的未提交改动，避免预览与上线版本不一致：\n' + '\n'.join(unexpected[:12]))
    return changed


def build(root):
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm:
        raise ValueError('本地预览需要 Node.js/npm。请安装 Node.js 22.12+ 并在项目目录运行 npm install。')
    run(root, [npm, 'run', 'build'], timeout=240)


def preview(catalog):
    catalog.local.mkdir(parents=True, exist_ok=True)
    validate_worktree(catalog)
    before = fingerprint(catalog)
    build(catalog.root)
    if fingerprint(catalog) != before:
        raise ValueError('构建期间照片发生变化，请重新预览。')
    validate_worktree(catalog)
    head = git(catalog.root, 'rev-parse', 'HEAD')
    branch = git(catalog.root, 'branch', '--show-current')
    token = uuid.uuid4().hex
    session = catalog.local / 'preview-session'
    session.write_text(token)
    ready = catalog.local / f'preview-{token}.json'
    command = [sys.executable, str(Path(__file__).with_name('preview_server.py')), '--root', str(catalog.root / 'dist'),
               '--session', str(session), '--token', token, '--ready', str(ready)]
    log_path = catalog.local / 'preview-server.log'
    with log_path.open('wb') as log:
        child = subprocess.Popen(command, cwd=catalog.root, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    for _ in range(600):
        if ready.exists():
            break
        if child.poll() is not None:
            raise ValueError('本地预览服务器启动失败：' + log_path.read_text(encoding='utf-8', errors='replace')[-2000:])
        time.sleep(.05)
    if not ready.exists():
        child.terminate()
        child.wait(timeout=5)
        raise ValueError('本地预览服务器启动超时。')
    info = read_json(ready, {})
    ready.unlink(missing_ok=True)
    threading.Thread(target=child.wait, daemon=True).start()
    url = f"http://127.0.0.1:{info['port']}/photos/"
    previous = read_json(catalog.local / 'review.json', {})
    review = {'fingerprint': before, 'head': head, 'branch': branch, 'url': url}
    # Retain the narrowly scoped pending commit across retries after a failed push.
    if previous.get('pendingCommit') == head:
        review['pendingCommit'] = head
        review['pendingParent'] = previous['pendingParent']
    atomic_json(catalog.local / 'review.json', review)
    return {'url': url, 'message': '本地预览已生成。检查照片后，再点击“确认并提交上线”。'}


def publish(catalog):
    root = catalog.root
    review_path = catalog.local / 'review.json'
    review = read_json(review_path, {})
    if not review or review.get('fingerprint') != fingerprint(catalog):
        raise ValueError('照片已变化或尚未预览，请先重新生成本地预览。')
    changes = validate_worktree(catalog)
    head = git(root, 'rev-parse', 'HEAD')
    branch = git(root, 'branch', '--show-current')
    if not branch or branch != review.get('branch') or head != review.get('head'):
        raise ValueError('Git 分支或提交已变化，请重新预览。')
    if branch != 'main':
        raise ValueError('当前网站由 main 分支部署，请切换到 main 后重新预览。')
    upstream = git(root, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
    if upstream != f'origin/{branch}':
        raise ValueError('当前分支必须跟踪 origin 上的同名分支。')
    git(root, 'fetch', 'origin', branch)
    remote = git(root, 'rev-parse', f'origin/{branch}')
    pending = review.get('pendingCommit') == head
    if remote != head and not (pending and remote == review.get('pendingParent')):
        raise ValueError('本地与远端存在其他未同步提交。请先在终端同步，再重新预览；不会自动合并或强推。')
    if changes:
        if pending:
            raise ValueError('上一笔照片提交尚未推送，且又有新修改。请先在终端同步后重新预览。')
        git(root, 'add', '--', *changes)
        try:
            git(root, 'commit', '-m', 'content: publish photography updates')
        except Exception:
            git(root, 'reset', '--', *changes)
            raise
        commit = git(root, 'rev-parse', 'HEAD')
        review.update({'pendingCommit': commit, 'pendingParent': head, 'head': commit})
        atomic_json(review_path, review)
    elif not pending:
        return {'message': '没有需要提交的照片修改。'}
    git(root, 'push', 'origin', f'HEAD:refs/heads/{branch}')
    review_path.unlink(missing_ok=True)
    return {'message': '照片修改已推送，GitHub Pages 正在部署。', 'commit': git(root, 'rev-parse', 'HEAD')}
