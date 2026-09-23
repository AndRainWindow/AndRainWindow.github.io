use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    env,
    fs,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{Arc, Mutex},
    thread,
};
use tauri::{AppHandle, Emitter, State};

#[derive(Default)]
struct TaskState {
    pid: Arc<Mutex<Option<u32>>>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ConfigView {
    vault: String,
    project: String,
    webp_enabled: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PythonInfo {
    available: bool,
    executable: String,
    version: String,
    publisher_ready: bool,
    error: Option<String>,
}

fn is_project_root(path: &Path) -> bool {
    path.is_dir()
        && path.join("package.json").is_file()
        && path.join("publisher").join("cli.py").is_file()
}

fn find_project_from(start: &Path) -> Option<PathBuf> {
    for candidate in start.ancestors() {
        if is_project_root(candidate) {
            return Some(candidate.to_path_buf());
        }
    }
    None
}

fn app_state_path() -> Result<PathBuf, String> {
    #[cfg(target_os = "windows")]
    {
        let base = env::var_os("APPDATA")
            .map(PathBuf::from)
            .or_else(|| {
                env::var_os("USERPROFILE")
                    .map(PathBuf::from)
                    .map(|p| p.join("AppData").join("Roaming"))
            })
            .ok_or_else(|| "无法确定 Windows AppData 目录".to_string())?;
        return Ok(base
            .join("AndRainWindow")
            .join("Publisher")
            .join("state.json"));
    }

    #[cfg(target_os = "macos")]
    {
        let home = env::var_os("HOME")
            .map(PathBuf::from)
            .ok_or_else(|| "无法确定 HOME 目录".to_string())?;
        return Ok(home
            .join("Library")
            .join("Application Support")
            .join("AndRainWindow")
            .join("Publisher")
            .join("state.json"));
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let base = env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .or_else(|| env::var_os("HOME").map(PathBuf::from).map(|p| p.join(".config")))
            .ok_or_else(|| "无法确定用户配置目录".to_string())?;
        return Ok(base.join("andrainwindow-publisher").join("state.json"));
    }
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

fn saved_project() -> Option<PathBuf> {
    let state = app_state_path().ok()?;
    let value = read_json(&state).ok()?;
    value
        .get("project")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(PathBuf::from)
}

fn save_project_pointer(project: &Path) -> Result<(), String> {
    let state = app_state_path()?;
    if let Some(parent) = state.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let content = serde_json::to_string_pretty(&json!({
        "project": project.to_string_lossy()
    }))
    .map_err(|e| e.to_string())?
        + "\n";
    fs::write(state, content).map_err(|e| e.to_string())
}

fn configured_project() -> Option<PathBuf> {
    if let Some(value) = env::var_os("ANDRAINWINDOW_PROJECT") {
        let path = PathBuf::from(value);
        if !path.as_os_str().is_empty() {
            return Some(path);
        }
    }

    if let Some(path) = saved_project() {
        return Some(path);
    }

    if let Ok(current) = env::current_dir() {
        if let Some(path) = find_project_from(&current) {
            return Some(path);
        }
    }

    if let Ok(exe) = env::current_exe() {
        if let Some(parent) = exe.parent() {
            if let Some(path) = find_project_from(parent) {
                return Some(path);
            }
        }
    }

    None
}

fn project_root() -> Result<PathBuf, String> {
    let path = configured_project().ok_or_else(|| {
        "尚未配置 Astro 项目目录。请先在 Settings 中选择项目并保存。".to_string()
    })?;
    if !is_project_root(&path) {
        return Err(format!(
            "项目目录无效：{}。需要包含 package.json 和 publisher/cli.py。",
            path.display()
        ));
    }
    Ok(path)
}

fn config_path(project: &Path) -> PathBuf {
    project.join("config.json")
}

fn site_config_path(project: &Path) -> PathBuf {
    project.join("site_config.json")
}

#[tauri::command]
fn get_config() -> Result<ConfigView, String> {
    let configured = configured_project();
    let project_text = configured
        .as_ref()
        .map(|p| p.to_string_lossy().into_owned())
        .unwrap_or_default();

    let Some(project) = configured else {
        return Ok(ConfigView {
            vault: String::new(),
            project: String::new(),
            webp_enabled: true,
        });
    };

    let path = config_path(&project);
    if !path.exists() {
        return Ok(ConfigView {
            vault: String::new(),
            project: project_text,
            webp_enabled: true,
        });
    }

    let value = read_json(&path)?;
    let vault = value
        .get("vault")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let project = value
        .get("project")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(ToString::to_string)
        .unwrap_or(project_text);
    let webp_enabled = value
        .get("webp")
        .and_then(|v| v.get("enabled"))
        .and_then(Value::as_bool)
        .unwrap_or(true);

    Ok(ConfigView {
        vault,
        project,
        webp_enabled,
    })
}

#[tauri::command]
fn save_config(config: ConfigView) -> Result<(), String> {
    let project = PathBuf::from(config.project.trim());
    if !is_project_root(&project) {
        return Err(format!(
            "项目目录无效：{}。需要包含 package.json 和 publisher/cli.py。",
            project.display()
        ));
    }

    let path = config_path(&project);
    let mut value = if path.exists() {
        read_json(&path)?
    } else {
        json!({})
    };

    let object = value
        .as_object_mut()
        .ok_or_else(|| "config.json 根节点必须是 JSON 对象".to_string())?;
    object.insert("vault".into(), Value::String(config.vault));
    object.insert(
        "project".into(),
        Value::String(project.to_string_lossy().into_owned()),
    );

    let webp = object.entry("webp").or_insert_with(|| json!({}));
    if !webp.is_object() {
        *webp = json!({});
    }
    webp.as_object_mut()
        .expect("webp was normalized to object")
        .insert("enabled".into(), Value::Bool(config.webp_enabled));

    let text = serde_json::to_string_pretty(&value).map_err(|e| e.to_string())? + "\n";
    fs::write(&path, text).map_err(|e| e.to_string())?;
    save_project_pointer(&project)
}

#[tauri::command]
fn validate_paths(vault: String, project: String) -> Vec<String> {
    let mut problems = Vec::new();
    let vault_path = PathBuf::from(&vault);
    let project_path = PathBuf::from(&project);

    if !vault.trim().is_empty() && !vault_path.is_dir() {
        problems.push(format!("Obsidian Vault 不存在：{vault}"));
    }
    if project.trim().is_empty() || !project_path.is_dir() {
        problems.push(format!("项目目录不存在：{project}"));
    } else {
        if !project_path.join("package.json").is_file() {
            problems.push(format!("目录不是 Astro 项目：{project}"));
        }
        if !project_path.join("publisher").join("cli.py").is_file() {
            problems.push(format!("项目缺少 publisher/cli.py：{project}"));
        }
    }
    problems
}

fn command_works(program: &str) -> bool {
    Command::new(program)
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn find_python() -> Result<String, String> {
    if let Ok(value) = env::var("PUBLISHER_PYTHON") {
        let value = value.trim();
        if !value.is_empty() {
            if command_works(value) {
                return Ok(value.to_string());
            }
            return Err(format!(
                "PUBLISHER_PYTHON 指向的 Python 不可用：{value}"
            ));
        }
    }

    for candidate in ["python", "python3"] {
        if command_works(candidate) {
            return Ok(candidate.to_string());
        }
    }

    Err("未找到 Python。请安装 Python 3，或设置 PUBLISHER_PYTHON 环境变量。".into())
}

#[tauri::command]
fn get_python_info() -> PythonInfo {
    let python = match find_python() {
        Ok(value) => value,
        Err(error) => {
            return PythonInfo {
                available: false,
                executable: String::new(),
                version: String::new(),
                publisher_ready: false,
                error: Some(error),
            }
        }
    };

    let version_output = Command::new(&python).arg("--version").output();
    let version = version_output
        .ok()
        .map(|output| {
            let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if stdout.is_empty() {
                String::from_utf8_lossy(&output.stderr).trim().to_string()
            } else {
                stdout
            }
        })
        .unwrap_or_default();

    let project = configured_project();
    let mut check = Command::new(&python);
    if let Some(root) = project.as_ref().filter(|p| is_project_root(p)) {
        check.current_dir(root);
    }
    let publisher_ready = check
        .args([
            "-c",
            "import publisher; from PIL import Image; print('ok')",
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false);

    PythonInfo {
        available: true,
        executable: python,
        version,
        publisher_ready,
        error: if publisher_ready {
            None
        } else {
            Some("Python 可用，但 Publisher/Pillow 依赖检查未通过。".to_string())
        },
    }
}

fn emit_line(app: &AppHandle, line: String) {
    let _ = app.emit("publisher://event", line);
}

#[tauri::command]
async fn photo_request(state: State<'_, TaskState>, payload: Value) -> Result<Value, String> {
    let slot = state.pid.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut guard = slot.lock().map_err(|_| "任务状态锁已损坏".to_string())?;
        if guard.is_some() {
            return Err("已有任务正在运行".to_string());
        }
        let root = project_root()?;
        let mut command = Command::new(find_python()?);
        command.current_dir(&root)
            .env("PYTHONUTF8", "1")
            .args(["-m", "publisher.cli", "photos", "--project"])
            .arg(&root)
            .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command.spawn().map_err(|e| format!("启动照片任务失败：{e}"))?;
        *guard = Some(child.id());
        drop(guard);
        let input = serde_json::to_vec(&payload).map_err(|e| e.to_string())?;
        let write_result = child.stdin.take().ok_or("无法打开任务输入".to_string())
            .and_then(|mut stream| stream.write_all(&input).map_err(|e| e.to_string()));
        if let Err(error) = write_result {
            let _ = child.kill();
            let _ = child.wait();
            if let Ok(mut guard) = slot.lock() { *guard = None; }
            return Err(error);
        }
        let output = child.wait_with_output();
        if let Ok(mut guard) = slot.lock() { *guard = None; }
        let output = output.map_err(|e| e.to_string())?;
        let response: Value = serde_json::from_slice(&output.stdout)
            .map_err(|_| format!("照片后端没有返回有效结果：{}", String::from_utf8_lossy(&output.stderr)))?;
        if !output.status.success() || response["type"] == "error" {
            return Err(response["message"].as_str().unwrap_or("照片操作失败").to_string());
        }
        Ok(response["result"].clone())
    }).await.map_err(|e| e.to_string())?
}

#[tauri::command]
fn open_preview(url: String) -> Result<(), String> {
    let port = url.strip_prefix("http://127.0.0.1:")
        .and_then(|s| s.strip_suffix("/photos/"))
        .and_then(|s| s.parse::<u16>().ok())
        .filter(|port| *port > 0)
        .ok_or_else(|| "仅允许打开本机摄影预览".to_string())?;
    let target = format!("http://127.0.0.1:{port}/photos/");
    #[cfg(target_os = "windows")]
    let mut command = { let mut c = Command::new("rundll32"); c.arg("url.dll,FileProtocolHandler"); c };
    #[cfg(target_os = "macos")]
    let mut command = Command::new("open");
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = Command::new("xdg-open");
    command.arg(target).spawn().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn start_task(app: AppHandle, state: State<TaskState>, task: String) -> Result<(), String> {
    if !["publish", "migrate-webp", "cleanup-webp", "validate"].contains(&task.as_str()) {
        return Err(format!("不支持的任务：{task}"));
    }

    let slot = state.pid.clone();
    let mut guard = slot
            .lock()
            .map_err(|_| "任务状态锁已损坏".to_string())?;
    if guard.is_some() {
        return Err("已有任务正在运行".into());
    }

    let python = find_python()?;
    let root = project_root()?;
    let mut command = Command::new(python);
    command
        .current_dir(&root)
        .arg("-m")
        .arg("publisher.cli")
        .arg("--config")
        .arg(config_path(&root))
        .arg("--site-config")
        .arg(site_config_path(&root))
        .arg(&task)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = command
        .spawn()
        .map_err(|e| format!("启动 Publisher 失败：{e}"))?;
    let pid = child.id();
    *guard = Some(pid);
    drop(guard);

    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let app_for_task = app.clone();
    let slot_for_task = slot.clone();

    thread::spawn(move || {
        if let Some(stderr) = stderr {
            let app_for_stderr = app_for_task.clone();
            thread::spawn(move || {
                for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                    emit_line(
                        &app_for_stderr,
                        json!({"type":"log","level":"error","message":line}).to_string(),
                    );
                }
            });
        }

        if let Some(stdout) = stdout {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                emit_line(&app_for_task, line);
            }
        }

        let status = child.wait();
        if let Ok(mut guard) = slot_for_task.lock() {
            *guard = None;
        }
        let code = status.ok().and_then(|s| s.code()).unwrap_or(-1);
        emit_line(
            &app_for_task,
            json!({"type":"process_exit","exitCode":code}).to_string(),
        );
    });

    Ok(())
}

#[tauri::command]
fn cancel_task(state: State<TaskState>) -> Result<(), String> {
    let pid = *state
        .pid
        .lock()
        .map_err(|_| "任务状态锁已损坏".to_string())?;
    let Some(pid) = pid else {
        return Ok(());
    };

    #[cfg(target_os = "windows")]
    let status = Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .status();

    #[cfg(not(target_os = "windows"))]
    let status = Command::new("kill")
        .args(["-TERM", &pid.to_string()])
        .status();

    status
        .map_err(|e| format!("取消任务失败：{e}"))?
        .success()
        .then_some(())
        .ok_or_else(|| "取消任务命令执行失败".to_string())
}

#[tauri::command]
fn open_folder(path: String) -> Result<(), String> {
    let target = PathBuf::from(&path);
    if !target.exists() {
        return Err(format!("路径不存在：{path}"));
    }

    #[cfg(target_os = "windows")]
    let mut command = Command::new("explorer");
    #[cfg(target_os = "macos")]
    let mut command = Command::new("open");
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = Command::new("xdg-open");

    command
        .arg(target)
        .spawn()
        .map_err(|e| format!("打开目录失败：{e}"))?;
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(TaskState::default())
        .on_window_event(|_, event| {
            if matches!(event, tauri::WindowEvent::Destroyed) {
                if let Some(root) = configured_project() {
                    let _ = fs::remove_file(root.join(".publisher-local/preview-session"));
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_config,
            save_config,
            validate_paths,
            get_python_info,
            start_task,
            cancel_task,
            photo_request,
            open_preview,
            open_folder
        ])
        .run(tauri::generate_context!())
        .expect("error while running AndRainWindow Publisher");
}
