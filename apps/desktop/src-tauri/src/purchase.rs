use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tauri::AppHandle;
use tauri_plugin_opener::OpenerExt;

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
pub struct PurchaseLaunchResult {
    mode: String,
    opened: bool,
    message: String,
}

fn load_payment(root: &Path) -> Result<RawService, String> {
    let content = std::fs::read_to_string(root.join("config/services.yaml"))
        .map_err(|error| format!("无法读取服务配置: {error}"))?;
    let mut config: RawConfig =
        serde_yaml::from_str(&content).map_err(|_| "服务配置格式无效".to_string())?;
    config
        .services
        .remove("payment")
        .ok_or_else(|| "服务配置缺少 payment".to_string())
}

fn mock_purchase_path(root: &Path) -> Result<PathBuf, String> {
    let root = root
        .canonicalize()
        .map_err(|error| format!("无法解析应用资源目录: {error}"))?;
    let path = root.join("fixtures/mock/purchase.html");
    let packaged_path = root.join("mock/purchase.html");
    let candidate = if path.is_file() { path } else { packaged_path };
    let candidate = candidate
        .canonicalize()
        .map_err(|_| "找不到随应用发布的 Mock 购买页".to_string())?;
    if !candidate.starts_with(&root) {
        return Err("Mock 购买页不在应用资源目录内".into());
    }
    Ok(candidate)
}

pub fn open(app: &AppHandle, root: &Path) -> Result<PurchaseLaunchResult, String> {
    let payment = load_payment(root)?;
    match payment.mode.as_str() {
        "mock" => {
            let path = mock_purchase_path(root)?;
            app.opener()
                .open_path(path.to_string_lossy(), None::<&str>)
                .map_err(|error| format!("无法使用系统浏览器打开 Mock 购买页: {error}"))?;
            let product = payment
                .mock
                .get("product_code")
                .and_then(Value::as_str)
                .unwrap_or("STT_DESKTOP_YEARLY_TEST");
            Ok(PurchaseLaunchResult {
                mode: "mock".into(),
                opened: true,
                message: format!(
                    "已在系统浏览器打开本地 Mock 购买页（{product}），不会产生真实订单或扣款"
                ),
            })
        }
        "real" => {
            Err("真实购买会话服务尚未接入；为防止账号错绑，不能直接打开无单次会话的购买页".into())
        }
        _ => Err("payment.mode 只允许 mock 或 real".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mock_page_must_resolve_inside_resource_root() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
        let resolved = mock_purchase_path(&root).expect("mock purchase fixture");
        assert!(resolved.ends_with(Path::new("fixtures/mock/purchase.html")));
    }

    #[test]
    fn payment_configuration_is_explicitly_mocked() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
        let payment = load_payment(&root).expect("payment config");
        assert_eq!(payment.mode, "mock");
        assert_eq!(
            payment.mock.get("amount_fen").and_then(Value::as_i64),
            Some(1)
        );
    }
}
