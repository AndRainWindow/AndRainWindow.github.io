import { useCallback, useEffect, useMemo, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { open } from '@tauri-apps/plugin-dialog';
import PhotosPage from './PhotosPage';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  FolderOpen,
  Home,
  Image as ImageIcon,
  LoaderCircle,
  Play,
  RefreshCw,
  Save,
  ScrollText,
  Send,
  Settings,
  Square,
  type LucideIcon,
} from 'lucide-react';

type Page = 'overview' | 'publish' | 'photos' | 'images' | 'logs' | 'settings';
type TaskName = 'publish' | 'migrate-webp' | 'cleanup-webp' | 'validate';
type RunState = 'idle' | 'running' | 'success' | 'error';

interface ConfigView {
  vault: string;
  project: string;
  webpEnabled: boolean;
}

interface PythonInfo {
  available: boolean;
  executable: string;
  version: string;
  publisherReady: boolean;
  error?: string | null;
}

interface BackendEvent {
  type: string;
  level?: string;
  message?: string;
  current?: number;
  total?: number;
  filename?: string;
  success?: number;
  failed?: number;
  skipped?: number;
  exitCode?: number;
  problems?: string[];
  ok?: boolean;
  summary?: Record<string, unknown>;
  count?: number;
}

interface NavItem {
  key: Page;
  label: string;
  icon: LucideIcon;
}

const navItems: NavItem[] = [
  { key: 'overview', label: 'Overview', icon: Home },
  { key: 'publish', label: 'Publish', icon: Send },
  { key: 'photos', label: '摄影管理', icon: ImageIcon },
  { key: 'images', label: 'Images', icon: ImageIcon },
  { key: 'logs', label: 'Logs', icon: ScrollText },
  { key: 'settings', label: 'Settings', icon: Settings },
];

const initialConfig: ConfigView = { vault: '', project: '', webpEnabled: true };

function App() {
  const [page, setPage] = useState<Page>('overview');
  const [config, setConfig] = useState<ConfigView>(initialConfig);
  const [draft, setDraft] = useState<ConfigView>(initialConfig);
  const [pythonInfo, setPythonInfo] = useState<PythonInfo | null>(null);
  const [pythonLoading, setPythonLoading] = useState(true);
  const [logs, setLogs] = useState<string[]>([]);
  const [runState, setRunState] = useState<RunState>('idle');
  const [busy, setBusy] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [currentFile, setCurrentFile] = useState('');
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [resultText, setResultText] = useState('尚未运行任务');
  const [validation, setValidation] = useState<string[]>([]);
  const [validationStatus, setValidationStatus] = useState<'idle' | 'checking' | 'success' | 'error'>('idle');

  useEffect(() => {
    setValidationStatus('idle');
    setValidation([]);
  }, [draft.vault, draft.project]);

  const appendLog = useCallback((line: string) => {
    setLogs((prev) => [...prev.slice(-399), line]);
  }, []);

  const refreshPythonInfo = useCallback(async () => {
    setPythonLoading(true);
    try {
      const value = await invoke<PythonInfo>('get_python_info');
      setPythonInfo(value);
    } catch (error) {
      setPythonInfo({
        available: false,
        executable: '',
        version: '',
        publisherReady: false,
        error: String(error),
      });
      appendLog(`[ERROR] Python 环境检查失败：${String(error)}`);
    } finally {
      setPythonLoading(false);
    }
  }, [appendLog]);

  const handleBackendEvent = useCallback((raw: string) => {
    let event: BackendEvent;
    try {
      event = JSON.parse(raw) as BackendEvent;
    } catch {
      appendLog(raw);
      return;
    }

    switch (event.type) {
      case 'start':
        setRunState('running');
        break;
      case 'progress':
        setProgress({ current: event.current ?? 0, total: event.total ?? 0 });
        break;
      case 'file':
        setCurrentFile(event.filename ?? '');
        break;
      case 'log':
        appendLog(`${event.level === 'error' ? '[ERROR] ' : ''}${event.message ?? ''}`);
        break;
      case 'validation':
        setValidation(event.problems ?? []);
        appendLog(event.ok ? '路径验证通过' : `路径验证失败：${(event.problems ?? []).join('；')}`);
        break;
      case 'complete': {
        setRunState('success');
        const pieces: string[] = [];
        if (typeof event.success === 'number') pieces.push(`成功 ${event.success}`);
        if (typeof event.failed === 'number') pieces.push(`失败 ${event.failed}`);
        if (typeof event.skipped === 'number') pieces.push(`跳过 ${event.skipped}`);
        if (typeof event.count === 'number') pieces.push(`处理 ${event.count}`);
        if (event.summary) pieces.push(JSON.stringify(event.summary));
        setResultText(pieces.join(' · ') || '任务完成');
        break;
      }
      case 'error':
        setRunState('error');
        setResultText(event.message ?? '任务失败');
        appendLog(`[ERROR] ${event.message ?? '任务失败'}`);
        break;
      case 'process_exit':
        setBusy(false);
        if ((event.exitCode ?? 1) !== 0) {
          setRunState('error');
          setResultText((prev) => (prev === '尚未运行任务' ? `进程退出码 ${event.exitCode}` : prev));
        }
        break;
      default:
        appendLog(raw);
    }
  }, [appendLog]);

  useEffect(() => {
    invoke<ConfigView>('get_config')
      .then((value) => {
        setConfig(value);
        setDraft(value);
      })
      .catch((error) => appendLog(`[ERROR] 读取配置失败：${String(error)}`));

    void refreshPythonInfo();

    const unlistenPromise = listen<string>('publisher://event', (event) => {
      handleBackendEvent(event.payload);
    });

    return () => {
      void unlistenPromise.then((unlisten) => unlisten());
    };
  }, [appendLog, handleBackendEvent, refreshPythonInfo]);

  const progressPercent = useMemo(() => {
    if (!progress.total) return 0;
    return Math.min(100, Math.round((progress.current / progress.total) * 100));
  }, [progress]);

  const backendReady = pythonInfo?.publisherReady === true;
  const pythonSummary = pythonLoading
    ? 'Checking…'
    : pythonInfo?.publisherReady
      ? pythonInfo.version || 'Ready'
      : pythonInfo?.available
        ? 'Needs dependencies'
        : 'Python not found';

  async function startTask(task: TaskName) {
    if (busy || photoBusy) return;
    if (!backendReady) {
      setResultText('Python / Publisher 环境尚未就绪');
      setPage('settings');
      return;
    }
    setBusy(true);
    setRunState('running');
    setCurrentFile('');
    setProgress({ current: 0, total: 0 });
    setResultText('正在运行…');
    appendLog(`> ${task}`);
    try {
      await invoke('start_task', { task });
    } catch (error) {
      setBusy(false);
      setRunState('error');
      setResultText(String(error));
      appendLog(`[ERROR] ${String(error)}`);
    }
  }

  async function cancelTask() {
    if (photoBusy) return;
    try {
      await invoke('cancel_task');
      appendLog('已请求取消当前任务');
    } catch (error) {
      appendLog(`[ERROR] 取消失败：${String(error)}`);
    }
  }

  async function pickDirectory(field: 'vault' | 'project') {
    const selected = await open({ directory: true, multiple: false });
    if (typeof selected === 'string') {
      setDraft((prev) => ({ ...prev, [field]: selected }));
    }
  }

  async function saveSettings() {
    if (busy || photoBusy) return;
    try {
      await invoke('save_config', { config: draft });
      setConfig(draft);
      setResultText('配置已保存');
      appendLog('配置已保存到 config.json');
      await refreshPythonInfo();
    } catch (error) {
      setResultText(`保存失败：${String(error)}`);
    }
  }

  async function validateSettings() {
    setValidationStatus('checking');
    setValidation([]);
    try {
      const problems = await invoke<string[]>('validate_paths', {
        vault: draft.vault.trim(),
        project: draft.project.trim(),
      });
      setValidation(problems);
      setValidationStatus(problems.length ? 'error' : 'success');
      appendLog(problems.length ? `路径验证失败：${problems.join('；')}` : '路径验证通过');
    } catch (error) {
      setValidationStatus('error');
      setValidation([`验证失败：${String(error)}`]);
      appendLog(`[ERROR] 路径验证失败：${String(error)}`);
    }
  }

  async function reveal(path: string) {
    if (!path) return;
    try {
      await invoke('open_folder', { path });
    } catch (error) {
      appendLog(`[ERROR] ${String(error)}`);
    }
  }

  function renderEnvironmentNotice() {
    if (pythonLoading || backendReady) return null;
    return (
      <div className="notice warning">
        <AlertTriangle size={17} />
        <div>
          <strong>Publisher 环境未就绪</strong>
          <span>{pythonInfo?.error || '请在 Settings 中检查 Python、Pillow 与项目目录。'}</span>
        </div>
        <button className="text-button inline" onClick={() => setPage('settings')}>检查设置</button>
      </div>
    );
  }

  function renderPage() {
    switch (page) {
      case 'publish':
        return (
          <PageShell title="Publish" subtitle="把 Obsidian 中标记为公开的笔记发布到 Astro 内容目录。">
            {renderEnvironmentNotice()}
            <TaskCard
              title="发布全部公开笔记"
              description="复用现有 Python Publisher；图片转换、封面、统计和正文处理逻辑都不会在 GUI 中重写。"
              busy={busy}
              disabled={!backendReady || photoBusy}
              actionLabel="开始发布"
              onRun={() => startTask('publish')}
              onCancel={cancelTask}
            />
            <ProgressPanel
              state={runState}
              percent={progressPercent}
              current={progress.current}
              total={progress.total}
              currentFile={currentFile}
              result={resultText}
            />
          </PageShell>
        );
      case 'images':
        return (
          <PageShell title="Images" subtitle="WebP 迁移与清理。迁移阶段默认保留原图。">
            {renderEnvironmentNotice()}
            <div className="card-grid two">
              <TaskCard
                title="迁移 public/images"
                description="扫描站点图片、生成 WebP，并更新本地引用。原图不会在这个步骤删除。"
                busy={busy}
                disabled={!backendReady || photoBusy}
                actionLabel="迁移到 WebP"
                onRun={() => startTask('migrate-webp')}
                onCancel={cancelTask}
              />
              <TaskCard
                title="清理旧原图"
                description="只应在站点 build 验证通过后执行。此操作会删除已被 WebP 替代的原图。"
                busy={busy}
                disabled={!backendReady || photoBusy}
                danger
                actionLabel="清理旧原图"
                onRun={() => {
                  if (window.confirm('确认已经完成构建验证，并删除被 WebP 替代的原图？')) {
                    void startTask('cleanup-webp');
                  }
                }}
                onCancel={cancelTask}
              />
            </div>
            <ProgressPanel
              state={runState}
              percent={progressPercent}
              current={progress.current}
              total={progress.total}
              currentFile={currentFile}
              result={resultText}
            />
          </PageShell>
        );
      case 'logs':
        return (
          <PageShell title="Logs" subtitle="Publisher 后端的实时 JSONL 事件和日志。">
            <section className="panel log-panel">
              <div className="panel-toolbar">
                <span>{logs.length} lines</span>
                <button className="button ghost" onClick={() => setLogs([])}>清空</button>
              </div>
              <pre className="log-view">{logs.length ? logs.join('\n') : '暂无日志。'}</pre>
            </section>
          </PageShell>
        );
      case 'settings':
        return (
          <PageShell title="Settings" subtitle="config.json 是 Publisher 与桌面 GUI 共用的配置源。">
            <section className="panel settings-panel">
              <PathField
                label="Obsidian Vault"
                value={draft.vault}
                onChange={(value) => setDraft((prev) => ({ ...prev, vault: value }))}
                onPick={() => pickDirectory('vault')}
                onReveal={() => reveal(draft.vault)}
              />
              <PathField
                label="Astro Project"
                value={draft.project}
                onChange={(value) => setDraft((prev) => ({ ...prev, project: value }))}
                onPick={() => pickDirectory('project')}
                onReveal={() => reveal(draft.project)}
              />
              <label className="switch-row">
                <div>
                  <strong>发布时转换 WebP</strong>
                  <span>沿用 Publisher 当前的 WebP quality presets。</span>
                </div>
                <input
                  type="checkbox"
                  checked={draft.webpEnabled}
                  onChange={(event) => setDraft((prev) => ({ ...prev, webpEnabled: event.target.checked }))}
                />
              </label>
              {validationStatus !== 'idle' && (
                <div className={`validation-box ${validationStatus}`} role="status" aria-live="polite">
                  {validationStatus === 'checking' && '正在验证路径…'}
                  {validationStatus === 'success' && `路径验证通过。若修改了目录，请点击“保存配置”。${draft.vault.trim() ? '' : 'Vault 未配置，仅可进行摄影管理。'}`}
                  {validationStatus === 'error' && validation.map((problem) => <div key={problem}>{problem}</div>)}
                </div>
              )}
              <div className="action-row">
                <button className="button secondary" disabled={validationStatus === 'checking'} onClick={() => void validateSettings()}>
                  <RefreshCw size={16} className={validationStatus === 'checking' ? 'spin' : ''} />
                  {validationStatus === 'checking' ? '验证中…' : '验证路径'}
                </button>
                <button className="button primary" disabled={busy || photoBusy} onClick={saveSettings}>
                  <Save size={16} /> 保存配置
                </button>
              </div>
            </section>
            <PythonPanel info={pythonInfo} loading={pythonLoading} onRefresh={refreshPythonInfo} />
          </PageShell>
        );
      default:
        return (
          <PageShell title="Overview" subtitle="Obsidian → Python Publisher → Astro 的桌面控制台。">
            <div className="hero-card">
              <div>
                <div className="eyebrow">AndRainWindow Publisher</div>
                <h2>内容发布，不重写已经工作的后端。</h2>
                <p>React + Tauri 只负责界面与进程桥接，核心发布逻辑仍由 Python Publisher 执行。</p>
              </div>
              <StatusBadge state={runState} />
            </div>
            {renderEnvironmentNotice()}
            <div className="card-grid four">
              <InfoCard title="Vault" value={config.vault || '未配置'} onOpen={() => reveal(config.vault)} />
              <InfoCard title="Project" value={config.project || '未配置'} onOpen={() => reveal(config.project)} />
              <InfoCard title="WebP" value={config.webpEnabled ? 'Enabled' : 'Disabled'} />
              <InfoCard
                title="Python"
                value={pythonSummary}
                detail={pythonInfo?.executable || pythonInfo?.error || ''}
                state={backendReady ? 'good' : pythonLoading ? 'neutral' : 'warning'}
              />
            </div>
            <section className="panel quick-panel">
              <div>
                <h3>Quick publish</h3>
                <p>直接执行一次完整发布，并在界面中显示当前文件、进度和日志。</p>
              </div>
              <button className="button primary" disabled={busy || photoBusy || !backendReady} onClick={() => startTask('publish')}>
                {busy ? <LoaderCircle size={17} className="spin" /> : <Play size={17} />}
                {busy ? '运行中' : '开始发布'}
              </button>
            </section>
            <ProgressPanel
              state={runState}
              percent={progressPercent}
              current={progress.current}
              total={progress.total}
              currentFile={currentFile}
              result={resultText}
            />
          </PageShell>
        );
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">AR</div>
          <div>
            <strong>AndRainWindow</strong>
            <span>Publisher</span>
          </div>
        </div>
        <nav className="sidebar-nav">
          {navItems.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              className={`nav-item ${page === key ? 'active' : ''}`}
              onClick={() => setPage(key)}
            >
              <Icon size={18} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className={`status-dot ${busy ? 'busy' : backendReady ? '' : 'warning'}`} />
          {busy ? 'Publisher running' : backendReady ? 'Environment ready' : 'Environment check'}
        </div>
      </aside>
      <main className="content-area">
        <div hidden={page !== 'photos'}>
          <PhotosPage active={page === 'photos'} project={config.project} disabled={busy || !backendReady} onBusy={setPhotoBusy} onLog={appendLog}/>
        </div>
        {page !== 'photos' && renderPage()}
      </main>
    </div>
  );
}

function PageShell({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="page">
      <header className="page-header">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </header>
      <div className="page-body">{children}</div>
    </div>
  );
}

function StatusBadge({ state }: { state: RunState }) {
  const content = {
    idle: ['Ready', Activity],
    running: ['Running', LoaderCircle],
    success: ['Completed', CheckCircle2],
    error: ['Needs attention', AlertTriangle],
  } as const;
  const [label, Icon] = content[state];
  return (
    <div className={`status-badge ${state}`}>
      <Icon size={16} className={state === 'running' ? 'spin' : ''} />
      {label}
    </div>
  );
}

function InfoCard({
  title,
  value,
  detail,
  state = 'neutral',
  onOpen,
}: {
  title: string;
  value: string;
  detail?: string;
  state?: 'neutral' | 'good' | 'warning';
  onOpen?: () => void;
}) {
  return (
    <section className={`info-card ${state}`}>
      <span>{title}</span>
      <strong title={value}>{value}</strong>
      {detail && <small title={detail}>{detail}</small>}
      {onOpen && (
        <button className="text-button" onClick={onOpen}>
          <FolderOpen size={15} /> 打开
        </button>
      )}
    </section>
  );
}

function PythonPanel({
  info,
  loading,
  onRefresh,
}: {
  info: PythonInfo | null;
  loading: boolean;
  onRefresh: () => void | Promise<void>;
}) {
  const ready = info?.publisherReady === true;
  const label = loading ? 'Checking' : ready ? 'Ready' : 'Needs setup';
  return (
    <section className="panel environment-panel">
      <div className="environment-heading">
        <div>
          <span className="section-label">Runtime environment</span>
          <h3>Python Publisher</h3>
          <p>桌面程序调用系统 Python，不内置第二份 Publisher 后端。</p>
        </div>
        <div className={`environment-chip ${ready ? 'good' : loading ? '' : 'warning'}`}>
          {loading ? <LoaderCircle size={15} className="spin" /> : ready ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
          {label}
        </div>
      </div>
      <div className="environment-grid">
        <div>
          <span>Executable</span>
          <strong>{info?.executable || '—'}</strong>
        </div>
        <div>
          <span>Version</span>
          <strong>{info?.version || '—'}</strong>
        </div>
        <div>
          <span>Publisher + Pillow</span>
          <strong>{ready ? 'Available' : 'Unavailable'}</strong>
        </div>
      </div>
      {info?.error && <div className="environment-error">{info.error}</div>}
      <div className="action-row">
        <button className="button secondary" disabled={loading} onClick={() => void onRefresh()}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} /> 重新检查
        </button>
      </div>
    </section>
  );
}

function TaskCard({
  title,
  description,
  busy,
  disabled = false,
  actionLabel,
  onRun,
  onCancel,
  danger = false,
}: {
  title: string;
  description: string;
  busy: boolean;
  disabled?: boolean;
  actionLabel: string;
  onRun: () => void;
  onCancel: () => void;
  danger?: boolean;
}) {
  return (
    <section className="panel task-card">
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      <div className="action-row">
        {busy && (
          <button className="button secondary" onClick={onCancel}>
            <Square size={15} /> 取消
          </button>
        )}
        <button className={`button ${danger ? 'danger' : 'primary'}`} disabled={busy || disabled} onClick={onRun}>
          {busy ? <LoaderCircle size={16} className="spin" /> : <Play size={16} />}
          {busy ? '任务运行中' : actionLabel}
        </button>
      </div>
    </section>
  );
}

function ProgressPanel({
  state,
  percent,
  current,
  total,
  currentFile,
  result,
}: {
  state: RunState;
  percent: number;
  current: number;
  total: number;
  currentFile: string;
  result: string;
}) {
  return (
    <section className="panel progress-panel">
      <div className="progress-heading">
        <div>
          <span className="section-label">Current task</span>
          <strong>{currentFile || result}</strong>
        </div>
        <StatusBadge state={state} />
      </div>
      <div className="progress-track">
        <div className="progress-bar" style={{ width: `${percent}%` }} />
      </div>
      <div className="progress-meta">
        <span>{total ? `${current} / ${total}` : 'Waiting for progress'}</span>
        <span>{percent}%</span>
      </div>
    </section>
  );
}

function PathField({
  label,
  value,
  onChange,
  onPick,
  onReveal,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onPick: () => void;
  onReveal: () => void;
}) {
  return (
    <div className="field-group">
      <label>{label}</label>
      <div className="path-row">
        <input value={value} onChange={(event) => onChange(event.target.value)} spellCheck={false} />
        <button className="icon-button" onClick={onPick} title="选择目录"><FolderOpen size={18} /></button>
        <button className="icon-button" onClick={onReveal} title="打开目录"><Activity size={18} /></button>
      </div>
    </div>
  );
}

export default App;
