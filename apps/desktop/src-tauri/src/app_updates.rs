use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::path::Path;
use tauri::{AppHandle, State};
use tauri_plugin_updater::{Update, UpdaterExt};

#[derive(Debug, Deserialize)]
struct RawConfig {
    services: HashMap<String, RawService>,
}

#[derive(Debug, Deserialize)]
struct RawService {
    mode: String,
    #[serde(default)]
    mock: HashMap<String, Value>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateStatus {
    mode: String,
    available: bool,
    current_version: String,
    version: Option<String>,
    notes: Option<String>,
    message: String,
}

pub struct PendingUpdate(pub Mutex<Option<Update>>);

impl Default for PendingUpdate {
    fn default() -> Self {
        Self(Mutex::new(None))
    }
}

fn update_service(root: &Path) -> Result<RawService, String> {
    let content = std::fs::read_to_string(root.join("config/services.yaml"))
        .map_err(|_| "无法读取更新服务配置".to_string())?;
    let mut config: RawConfig =
        serde_yaml::from_str(&content).map_err(|_| "更新服务配置格式无效".to_string())?;
    config
        .services
        .remove("updates")
        .ok_or_else(|| "服务配置缺少 updates".to_string())
}

pub async fn check(
    app: AppHandle,
    root: &Path,
    pending: State<'_, PendingUpdate>,
) -> Result<UpdateStatus, String> {
    let service = update_service(root)?;
    let current_version = app.package_info().version.to_string();
    if service.mode == "mock" {
        pending.0.lock().take();
        let available = service
            .mock
            .get("update_available")
            .and_then(Value::as_bool)
            .unwrap_or(false);
        return Ok(UpdateStatus {
            mode: "mock".into(),
            available: false,
            current_version,
            version: None,
            notes: None,
            message: if available {
                "Mock 清单声明有更新，但测试模式禁止安装未签名远程制品".into()
            } else {
                "Mock 更新服务：当前已是最新版本".into()
            },
        });
    }
    if service.mode != "real" {
        return Err("updates.mode 只允许 mock 或 real".into());
    }

    let update = app
        .updater()
        .map_err(|error| format!("更新器初始化失败: {error}"))?
        .check()
        .await
        .map_err(|error| format!("检查更新失败: {error}"))?;
    let status = if let Some(update) = update.as_ref() {
        UpdateStatus {
            mode: "real".into(),
            available: true,
            current_version,
            version: Some(update.version.clone()),
            notes: update.body.clone(),
            message: format!("发现新版本 {}", update.version),
        }
    } else {
        UpdateStatus {
            mode: "real".into(),
            available: false,
            current_version,
            version: None,
            notes: None,
            message: "当前已是最新版本".into(),
        }
    };
    *pending.0.lock() = update;
    Ok(status)
}

pub async fn install(pending: State<'_, PendingUpdate>) -> Result<(), String> {
    let update = pending
        .0
        .lock()
        .take()
        .ok_or_else(|| "没有已校验且待安装的更新".to_string())?;
    update
        .download_and_install(|_, _| {}, || {})
        .await
        .map_err(|error| format!("下载或安装更新失败: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mock_update_defaults_to_unavailable() {
        let service: RawService = serde_yaml::from_str("mode: mock\nmock: {}\n").unwrap();
        assert_eq!(service.mode, "mock");
        assert!(!service
            .mock
            .get("update_available")
            .and_then(Value::as_bool)
            .unwrap_or(false));
    }
}
