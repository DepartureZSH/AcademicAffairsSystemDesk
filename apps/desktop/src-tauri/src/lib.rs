mod access_gate;

use hmac::{Hmac, Mac};
use parking_lot::Mutex;
use rand::RngCore;
use reqwest::Method;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::Sha256;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::time::Duration;
use tauri::{AppHandle, Manager, RunEvent, State};

const PROTOCOL_VERSION: &str = "1";

#[derive(Default)]
struct SidecarManager {
    runtime: Option<SidecarRuntime>,
}

struct SidecarRuntime {
    child: Child,
    token: String,
    base_url: String,
    port: u16,
    pid: u32,
    workspace_path: PathBuf,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ReadyMessage {
    event: String,
    port: u16,
    pid: u32,
    protocol_version: String,
    nonce_proof: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeStatus {
    running: bool,
    port: Option<u16>,
    pid: Option<u32>,
    protocol_version: Option<String>,
    workspace_path: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProxyRequest {
    method: String,
    path: String,
    body: Option<Value>,
}

fn random_hex(bytes: usize) -> String {
    let mut data = vec![0_u8; bytes];
    rand::rng().fill_bytes(&mut data);
    hex::encode(data)
}

#[cfg(debug_assertions)]
fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../.."))
}

fn runtime_root(app: &AppHandle) -> Result<PathBuf, String> {
    #[cfg(debug_assertions)]
    {
        let root = repository_root();
        if root.join("config/services.yaml").is_file() {
            return Ok(root);
        }
    }
    app.path()
        .resource_dir()
        .map_err(|error| format!("无法确定应用资源目录: {error}"))
}

struct SidecarLaunch {
    executable: PathBuf,
    arguments: Vec<String>,
    environment: Vec<(String, String)>,
}

#[cfg(all(windows, debug_assertions))]
fn windows_development_python(root: &Path) -> Result<SidecarLaunch, String> {
    let virtual_environment = root.join(".venv");
    let configuration_path = virtual_environment.join("pyvenv.cfg");
    let configuration = std::fs::read_to_string(&configuration_path)
        .map_err(|error| format!("无法读取开发环境 pyvenv.cfg: {error}"))?;
    let home = configuration
        .lines()
        .find_map(|line| line.strip_prefix("home = "))
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or("开发环境 pyvenv.cfg 缺少 home")?;
    let executable = PathBuf::from(home).join("python.exe");
    if !executable.is_file() {
        return Err("开发环境对应的 CPython 不存在，请重新执行 uv sync --extra dev".into());
    }
    let python_path = std::env::join_paths([
        root.join("sidecar"),
        virtual_environment.join("Lib/site-packages"),
    ])
    .map_err(|error| format!("无法构造开发环境 PYTHONPATH: {error}"))?
    .to_string_lossy()
    .into_owned();
    Ok(SidecarLaunch {
        executable,
        arguments: vec!["-m".into(), "stt_desktop.sidecar_main".into()],
        environment: vec![
            (
                "VIRTUAL_ENV".into(),
                virtual_environment.to_string_lossy().into_owned(),
            ),
            ("PYTHONPATH".into(), python_path),
        ],
    })
}

fn sidecar_launch(_root: &Path) -> Result<SidecarLaunch, String> {
    if let Ok(path) = std::env::var("STT_SIDECAR_EXECUTABLE") {
        let candidate = PathBuf::from(path);
        if candidate.is_file() {
            return Ok(SidecarLaunch {
                executable: candidate,
                arguments: Vec::new(),
                environment: Vec::new(),
            });
        }
        return Err("STT_SIDECAR_EXECUTABLE 指向的文件不存在".into());
    }
    #[cfg(all(windows, debug_assertions))]
    if _root.join(".venv/Scripts/python.exe").is_file() {
        return windows_development_python(_root);
    }
    #[cfg(not(windows))]
    let development = _root.join(".venv/bin/python");
    #[cfg(not(windows))]
    if development.is_file() {
        return Ok(SidecarLaunch {
            executable: development,
            arguments: vec!["-m".into(), "stt_desktop.sidecar_main".into()],
            environment: Vec::new(),
        });
    }
    let installed = std::env::current_exe()
        .map_err(|error| format!("无法确定桌面程序路径: {error}"))?
        .parent()
        .ok_or("桌面程序路径缺少父目录")?
        .join(if cfg!(windows) {
            "stt-sidecar.exe"
        } else {
            "stt-sidecar"
        });
    if installed.is_file() {
        return Ok(SidecarLaunch {
            executable: installed,
            arguments: Vec::new(),
            environment: Vec::new(),
        });
    }
    Err("找不到随安装包发布的 Python sidecar；请重新安装应用".into())
}

fn status_from_runtime(runtime: Option<&SidecarRuntime>) -> RuntimeStatus {
    RuntimeStatus {
        running: runtime.is_some(),
        port: runtime.map(|item| item.port),
        pid: runtime.map(|item| item.pid),
        protocol_version: runtime.map(|_| PROTOCOL_VERSION.to_owned()),
        workspace_path: runtime.map(|item| item.workspace_path.to_string_lossy().into_owned()),
    }
}

#[tauri::command]
fn runtime_status(state: State<'_, Mutex<SidecarManager>>) -> RuntimeStatus {
    let mut manager = state.lock();
    if let Some(runtime) = manager.runtime.as_mut() {
        if matches!(runtime.child.try_wait(), Ok(Some(_))) {
            manager.runtime = None;
        }
    }
    status_from_runtime(manager.runtime.as_ref())
}

#[tauri::command]
fn start_sidecar(
    app: AppHandle,
    state: State<'_, Mutex<SidecarManager>>,
    workspace_path: Option<String>,
) -> Result<RuntimeStatus, String> {
    let mut manager = state.lock();
    if let Some(runtime) = manager.runtime.as_mut() {
        if matches!(runtime.child.try_wait(), Ok(None)) {
            return Ok(status_from_runtime(Some(runtime)));
        }
        manager.runtime = None;
    }

    let root = runtime_root(&app)?;
    access_gate::ensure_sidecar_allowed(&root)?;
    let launch = sidecar_launch(&root)?;
    let services_config = root.join("config/services.yaml");
    if !services_config.is_file() {
        return Err("找不到 config/services.yaml".into());
    }
    let workspace = match workspace_path {
        Some(path) if !path.trim().is_empty() => PathBuf::from(path),
        _ => app
            .path()
            .app_data_dir()
            .map_err(|error| format!("无法确定应用数据目录: {error}"))?
            .join("Workspace"),
    };
    std::fs::create_dir_all(&workspace).map_err(|error| format!("无法创建工作目录: {error}"))?;
    let workspace = workspace
        .canonicalize()
        .map_err(|error| format!("无法解析工作目录: {error}"))?;
    let token = random_hex(32);
    let nonce = random_hex(16);
    let mut command = Command::new(launch.executable);
    command
        .args(launch.arguments)
        .envs(launch.environment)
        .current_dir(&root)
        .env("STT_SIDECAR_TOKEN", &token)
        .env("STT_SIDECAR_NONCE", &nonce)
        .env("STT_WORKSPACE_PATH", &workspace)
        .env("STT_SERVICES_CONFIG", &services_config)
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    let mut child = command
        .spawn()
        .map_err(|error| format!("无法启动 sidecar: {error}"))?;
    let stdout = child.stdout.take().ok_or("无法读取 sidecar 就绪消息")?;
    let (sender, receiver) = mpsc::sync_channel(1);
    std::thread::spawn(move || {
        let mut line = String::new();
        let result = BufReader::new(stdout)
            .read_line(&mut line)
            .map(|_| line)
            .map_err(|error| error.to_string());
        let _ = sender.send(result);
    });
    let line = match receiver.recv_timeout(Duration::from_secs(10)) {
        Ok(Ok(line)) => line,
        Ok(Err(error)) => {
            let _ = child.kill();
            return Err(format!("读取 sidecar 就绪消息失败: {error}"));
        }
        Err(_) => {
            let _ = child.kill();
            return Err("sidecar 10 秒内未就绪".into());
        }
    };
    let ready: ReadyMessage =
        serde_json::from_str(&line).map_err(|_| "sidecar 就绪消息格式无效")?;
    if ready.event != "ready"
        || ready.protocol_version != PROTOCOL_VERSION
        || ready.pid != child.id()
    {
        let _ = child.kill();
        return Err("sidecar 身份或协议版本校验失败".into());
    }
    let proof = hex::decode(&ready.nonce_proof).map_err(|_| "sidecar nonce 证明格式无效")?;
    let mut mac =
        Hmac::<Sha256>::new_from_slice(token.as_bytes()).map_err(|_| "无法初始化 HMAC")?;
    mac.update(nonce.as_bytes());
    if mac.verify_slice(&proof).is_err() {
        let _ = child.kill();
        return Err("sidecar nonce 证明校验失败".into());
    }
    manager.runtime = Some(SidecarRuntime {
        child,
        token,
        base_url: format!("http://127.0.0.1:{}", ready.port),
        port: ready.port,
        pid: ready.pid,
        workspace_path: workspace,
    });
    Ok(status_from_runtime(manager.runtime.as_ref()))
}

#[tauri::command]
async fn access_gate_status(app: AppHandle) -> Result<access_gate::GateStatus, String> {
    access_gate::status(&runtime_root(&app)?).await
}

#[tauri::command]
async fn auth_sign_in(
    app: AppHandle,
    email: String,
    password: String,
) -> Result<access_gate::GateStatus, String> {
    access_gate::sign_in(&runtime_root(&app)?, email, password).await
}

#[tauri::command]
async fn auth_sign_up(
    app: AppHandle,
    email: String,
    password: String,
) -> Result<access_gate::AuthStatus, String> {
    access_gate::sign_up(&runtime_root(&app)?, email, password).await
}

#[tauri::command]
async fn auth_request_password_reset(app: AppHandle, email: String) -> Result<String, String> {
    access_gate::request_password_reset(&runtime_root(&app)?, email).await
}

#[tauri::command]
async fn auth_sign_out(app: AppHandle) -> Result<access_gate::GateStatus, String> {
    access_gate::sign_out(&runtime_root(&app)?).await
}

#[tauri::command]
async fn license_activate(
    app: AppHandle,
    enterprise_key: String,
) -> Result<access_gate::GateStatus, String> {
    access_gate::activate(&runtime_root(&app)?, enterprise_key).await
}

impl Drop for SidecarRuntime {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn terminate_managed_sidecar(app: &AppHandle) {
    let state = app.state::<Mutex<SidecarManager>>();
    let runtime = state.lock().runtime.take();
    if let Some(mut runtime) = runtime {
        let _ = runtime.child.kill();
        let _ = runtime.child.wait();
    }
}

fn validate_proxy_request(request: &ProxyRequest) -> Result<Method, String> {
    if !request.path.starts_with("/v1/")
        || request.path.contains("://")
        || request.path.contains("..")
        || request.path.contains('\n')
        || request.path.contains('\r')
    {
        return Err("sidecar 路径不在 /v1 白名单".into());
    }
    match request.method.as_str() {
        "GET" => Ok(Method::GET),
        "POST" => Ok(Method::POST),
        "PUT" => Ok(Method::PUT),
        "DELETE" => Ok(Method::DELETE),
        _ => Err("不支持的 sidecar HTTP 方法".into()),
    }
}

#[tauri::command]
async fn sidecar_request(
    state: State<'_, Mutex<SidecarManager>>,
    request: ProxyRequest,
) -> Result<Value, String> {
    let method = validate_proxy_request(&request)?;
    let (url, token) = {
        let manager = state.lock();
        let runtime = manager.runtime.as_ref().ok_or("本地服务尚未启动")?;
        (
            format!("{}{}", runtime.base_url, request.path),
            runtime.token.clone(),
        )
    };
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|error| format!("无法创建本地请求: {error}"))?;
    let mut builder = client.request(method, url).bearer_auth(token);
    if let Some(body) = request.body {
        builder = builder.json(&body);
    }
    let response = builder
        .send()
        .await
        .map_err(|error| format!("本地服务请求失败: {error}"))?;
    let status = response.status();
    let payload: Value = response
        .json()
        .await
        .map_err(|_| "本地服务返回了无效 JSON")?;
    if !status.is_success() {
        return Err(payload.to_string());
    }
    Ok(payload)
}

#[tauri::command]
async fn stop_sidecar(state: State<'_, Mutex<SidecarManager>>) -> Result<(), String> {
    let runtime = state.lock().runtime.take();
    if let Some(mut runtime) = runtime {
        let _ = reqwest::Client::new()
            .post(format!("{}/v1/projects/current/close", runtime.base_url))
            .bearer_auth(&runtime.token)
            .timeout(Duration::from_secs(3))
            .send()
            .await;
        runtime
            .child
            .kill()
            .map_err(|error| format!("无法停止 sidecar: {error}"))?;
        let _ = runtime.child.wait();
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let application = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(Mutex::new(SidecarManager::default()))
        .invoke_handler(tauri::generate_handler![
            runtime_status,
            access_gate_status,
            auth_sign_in,
            auth_sign_up,
            auth_request_password_reset,
            auth_sign_out,
            license_activate,
            start_sidecar,
            sidecar_request,
            stop_sidecar
        ])
        .build(tauri::generate_context!())
        .expect("error while building the desktop application");
    application.run(|app, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            terminate_managed_sidecar(app);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(method: &str, path: &str) -> ProxyRequest {
        ProxyRequest {
            method: method.into(),
            path: path.into(),
            body: None,
        }
    }

    #[test]
    fn proxy_accepts_versioned_local_api_paths() {
        assert_eq!(
            validate_proxy_request(&request("GET", "/v1/projects")),
            Ok(Method::GET)
        );
        assert_eq!(
            validate_proxy_request(&request("POST", "/v1/projects/current/close")),
            Ok(Method::POST)
        );
    }

    #[test]
    fn proxy_rejects_path_and_method_injection() {
        assert!(validate_proxy_request(&request("GET", "http://example.invalid/v1/x")).is_err());
        assert!(validate_proxy_request(&request("GET", "/v1/../secrets")).is_err());
        assert!(validate_proxy_request(&request("PATCH", "/v1/projects")).is_err());
    }
}
