use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    env,
    fs,
    io::{BufRead, BufReader},
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

fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("desktop/src-tauri must be inside the repository")
        .to_path_buf()
}

fn config_path() -> PathBuf {
    project_root().join("config.json")
}

fn site_config_path() -> PathBuf {
    project_root().join("site_config.json")
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_config() -> Result<ConfigView, String> {
    let root = project_root();
    let path = config_path();
    if !path.exists() {
        return Ok(ConfigView {
            vault: String::new(),
            project: root.to_string_lossy().into_owned(),
            webp_enabled: true,
        });
    }

    let value = read_json(&path)?;
    let vault = value.get("vault").and_then(Value::as_str).unwrap_or("").to_string();
    let project = value
        .get("project")
        .and_then(Value::as_str)
        .map(ToString::to_string)
        .unwrap_or_else(|| root.to_string_lossy().into_owned());
    let webp_enabled = value
        .get("webp")
        .and_then(|v| v.get("enabled"))
        .and_then(Value::as_bool)
        .unwrap_or(true);

    Ok(ConfigView { vault, project, webp_enabled })
}

#[tauri::command]
fn save_config(config: ConfigView) -> Result<(), String> {
    let path = config_path();
    let mut value = if path.exists() {
        read_json(&path)?
    } else {
        json!({})
    };

    let object = value
        .as_object_mut()
        .ok_or_else(|| "config.json 根节点必须是 JSON 对象".to_string())?;
    object.insert("vault".into(), Value::String(config.vault));
    object.insert("project".into(), Value::String(config.project));

    let webp = object.entry("webp").or_insert_with(|| json!({}));
    if !webp.is_object() {
        *webp = json!({});
    }
    webp.as_object_mut()
        .expect("webp was normalized to object")
        .insert("enabled".into(), Value::Bool(config.webp_enabled));

    let text = serde_json::to_string_pretty(&value).map_err(|e| e.to_string())? + "\n";
    fs::write(path, text).map_err(|e| e.to_string())
}

#[tauri::command]
fn validate_paths(vault: String, project: String) -> Vec<String> {
    let mut problems = Vec::new();
    let vault_path = PathBuf::from(&vault);
    let project_path = PathBuf::from(&project);

    if vault.trim().is_empty() || !vault_path.is_dir() {
        problems.push(format!("Obsidian Vault 不存在：{vault}"));
    }
    if project.trim().is_empty() || !project_path.is_dir() {
        problems.push(format!("项目目录不存在：{project}"));
    } else if !project_path.join("package.json").is_file() {
        problems.push(format!("目录不是 Astro 项目：{project}"));
    }
    problems
}

fn find_python() -> Result<String, String> {
    if let Ok(value) = env::var("PUBLISHER_PYTHON") {
        if !value.trim().is_empty() {
            return Ok(value);
        }
    }

    for candidate in ["python", "python3"] {
        if Command::new(candidate)
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|status| status.success())
            .unwrap_or(false)
        {
            return Ok(candidate.to_string());
        }
    }

    Err("未找到 Python。请安装 Python 3，或设置 PUBLISHER_PYTHON 环境变量。".into())
}

fn emit_line(app: &AppHandle, line: String) {
    let _ = app.emit("publisher://event", line);
}

#[tauri::command]
fn start_task(app: AppHandle, state: State<TaskState>, task: String) -> Result<(), String> {
    if !["publish", "migrate-webp", "cleanup-webp", "validate"].contains(&task.as_str()) {
        return Err(format!("不支持的任务：{task}"));
    }

    let slot = state.pid.clone();
    {
        let guard = slot.lock().map_err(|_| "任务状态锁已损坏".to_string())?;
        if guard.is_some() {
            return Err("已有任务正在运行".into());
        }
    }

    let python = find_python()?;
    let root = project_root();
    let mut command = Command::new(python);
    command
        .current_dir(&root)
        .arg("-m")
        .arg("publisher.cli")
        .arg("--config")
        .arg(config_path())
        .arg("--site-config")
        .arg(site_config_path())
        .arg(&task)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = command.spawn().map_err(|e| format!("启动 Publisher 失败：{e}"))?;
    let pid = child.id();
    *slot.lock().map_err(|_| "任务状态锁已损坏".to_string())? = Some(pid);

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
    let pid = *state.pid.lock().map_err(|_| "任务状态锁已损坏".to_string())?;
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
        .invoke_handler(tauri::generate_handler![
            get_config,
            save_config,
            validate_paths,
            start_task,
            cancel_task,
            open_folder
        ])
        .run(tauri::generate_context!())
        .expect("error while running AndRainWindow Publisher");
}
