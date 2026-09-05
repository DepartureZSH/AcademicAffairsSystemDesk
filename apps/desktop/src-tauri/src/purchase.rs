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
    endpoint: Option<String>,
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
            let endpoint = payment.endpoint.ok_or("尚未配置网页版会员入口")?;
            let url = reqwest::Url::parse(&endpoint).map_err(|_| "网页版会员入口格式无效")?;
            if url.scheme() != "https"
                || !url.username().is_empty()
                || url.password().is_some()
                || url.query().is_some()
                || url.fragment().is_some()
            {
                return Err("网页版会员入口必须使用不含账号凭据的 HTTPS 地址".into());
            }
            app.opener()
                .open_url(url.as_str(), None::<&str>)
                .map_err(|_| "无法打开网页版会员入口")?;
            Ok(PurchaseLaunchResult {
                mode: "real".into(),
                opened: true,
                message: "已打开网页版，请使用与桌面端相同的账号登录后开通会员，再返回检查权益"
                    .into(),
            })
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
    fn payment_configuration_uses_web_account_membership() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
        let payment = load_payment(&root).expect("payment config");
        assert_eq!(payment.mode, "real");
        assert_eq!(
            payment.endpoint.as_deref(),
            Some("https://dean.karios.site/login")
        );
    }
}
