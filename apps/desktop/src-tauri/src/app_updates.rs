use parking_lot::Mutex;
use semver::Version;
use serde::{Deserialize, Serialize};
use std::{path::Path, time::Duration};
use tauri::{ipc::Channel, AppHandle, State};
use tauri_plugin_updater::{Update, UpdaterExt};

const REPO: &str = "https://gitee.com/hangzhou-greos-time/academic-affairs-system-desk";
const API: &str =
    "https://gitee.com/api/v5/repos/hangzhou-greos-time/academic-affairs-system-desk/releases";

#[derive(Debug, Deserialize)]
struct Release {
    tag_name: String,
    #[serde(default)]
    draft: bool,
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

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DownloadProgress {
    downloaded: u64,
    total: Option<u64>,
}

#[derive(Default)]
struct Pending {
    update: Option<Update>,
    bytes: Option<Vec<u8>>,
    busy: bool,
}
#[derive(Default)]
pub struct PendingUpdate(Mutex<Pending>);
struct Operation<'a>(&'a PendingUpdate);
impl Drop for Operation<'_> {
    fn drop(&mut self) {
        self.0 .0.lock().busy = false;
    }
}
fn begin(pending: &PendingUpdate) -> Result<Operation<'_>, String> {
    let mut state = pending.0.lock();
    if state.busy {
        return Err("更新操作正在进行，请稍候".into());
    }
    state.busy = true;
    Ok(Operation(pending))
}

fn latest(releases: &[Release]) -> Option<(&Release, Version)> {
    releases
        .iter()
        .filter(|r| !r.draft)
        .filter_map(|r| {
            Version::parse(r.tag_name.strip_prefix('v').unwrap_or(&r.tag_name))
                .ok()
                .map(|v| (r, v))
        })
        .max_by(|a, b| a.1.cmp(&b.1))
}
fn valid_download(url: &str, tag: &str) -> bool {
    url.starts_with(&format!("{REPO}/releases/download/{tag}/"))
        && !url.contains('?')
        && !url.contains('#')
        && !url.contains("/../")
}

pub async fn check(
    app: AppHandle,
    _root: &Path,
    pending: State<'_, PendingUpdate>,
) -> Result<UpdateStatus, String> {
    let _operation = begin(&pending)?;
    {
        let mut state = pending.0.lock();
        state.update = None;
        state.bytes = None;
    }
    let current = app.package_info().version.clone();
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(30))
        .user_agent("STT-Desktop-Updater")
        .build()
        .map_err(|_| "无法初始化更新连接")?;
    let mut releases = Vec::new();
    for page in 1..=10 {
        let response = client
            .get(format!("{API}?page={page}&per_page=100"))
            .send()
            .await
            .map_err(|_| "无法连接 Gitee，请检查网络后重试")?;
        if !response.status().is_success() {
            return Err(format!(
                "Gitee 查询失败（HTTP {}），请稍后重试",
                response.status().as_u16()
            ));
        }
        let items: Vec<Release> = response
            .json()
            .await
            .map_err(|_| "Gitee 返回的版本列表格式异常")?;
        let done = items.len() < 100;
        releases.extend(items);
        if done {
            break;
        }
        if page == 10 {
            return Err("版本列表过长，无法可靠确定最新版本".into());
        }
    }
    let (release, version) = latest(&releases).ok_or("Gitee 暂无可识别的发布版本")?;
    if version <= current {
        return Ok(UpdateStatus {
            mode: "real".into(),
            available: false,
            current_version: current.to_string(),
            version: Some(version.to_string()),
            notes: None,
            message: "当前已是最新版本（含内测版）".into(),
        });
    }
    let endpoint = format!(
        "{REPO}/releases/download/{}/latest-beta.json",
        release.tag_name
    );
    let mut update = app
        .updater_builder()
        .endpoints(vec![endpoint.parse().map_err(|_| "更新地址无效")?])
        .map_err(|_| "更新地址无效")?
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|_| "更新器初始化失败")?
        .check()
        .await
        .map_err(|_| {
            "发现新版，但无法读取有效更新清单。请稍后重试或联系发布者补齐 latest-beta.json 和签名"
        })?
        .ok_or("发布标签与更新清单版本不一致")?;
    if update.version != version.to_string()
        || !valid_download(update.download_url.as_str(), &release.tag_name)
        || update.signature.trim().is_empty()
    {
        return Err("更新清单的版本、下载地址或签名不符合要求，已阻止下载".into());
    }
    update.timeout = Some(Duration::from_secs(1800));
    let status = UpdateStatus {
        mode: "real".into(),
        available: true,
        current_version: current.to_string(),
        version: Some(update.version.clone()),
        notes: update.body.clone(),
        message: format!("发现新版本 {}，正在下载", update.version),
    };
    pending.0.lock().update = Some(update);
    Ok(status)
}

pub async fn download(
    pending: State<'_, PendingUpdate>,
    progress: Channel<DownloadProgress>,
) -> Result<(), String> {
    let _operation = begin(&pending)?;
    let update = pending.0.lock().update.clone().ok_or("请先检查更新")?;
    pending.0.lock().bytes = None;
    let mut downloaded = 0;
    let bytes = update
        .download(
            |size, total| {
                downloaded += size as u64;
                let _ = progress.send(DownloadProgress { downloaded, total });
            },
            || {},
        )
        .await
        .map_err(|_| "更新包下载或签名校验失败，未执行安装。请检查网络后重试")?;
    // The plugin verifies the signature before returning these bytes.
    pending.0.lock().bytes = Some(bytes);
    Ok(())
}

pub async fn install(app: AppHandle, pending: State<'_, PendingUpdate>) -> Result<(), String> {
    let _operation = begin(&pending)?;
    let (update, bytes) = {
        let mut state = pending.0.lock();
        let update = state.update.clone().ok_or("请先检查更新")?;
        let bytes = state.bytes.take().ok_or("请先下载并通过签名校验")?;
        (update, bytes)
    };
    use tauri::Manager;
    if let Err(error) = super::stop_sidecar(app.state()).await {
        pending.0.lock().bytes = Some(bytes);
        return Err(format!("尚未安装：{error}"));
    }
    let result = update
        .install(&bytes)
        .map_err(|_| "安装更新失败，请关闭其他应用实例后重试".to_string());
    if result.is_err() {
        pending.0.lock().bytes = Some(bytes);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn selects_semver_including_beta_not_api_order() {
        let list: Vec<Release> = serde_json::from_str(r#"[{"tag_name":"v0.2.9"},{"tag_name":"v0.2.10-beta.1"},{"tag_name":"v9.0.0","draft":true},{"tag_name":"invalid"}]"#).unwrap();
        assert_eq!(latest(&list).unwrap().1.to_string(), "0.2.10-beta.1");
    }
    #[test]
    fn rejects_foreign_downloads() {
        assert!(valid_download(
            &format!("{REPO}/releases/download/v0.2.7/STT.exe"),
            "v0.2.7"
        ));
        assert!(!valid_download("https://evil.example/STT.exe", "v0.2.7"));
        assert!(!valid_download(
            &format!("{REPO}/releases/download/v0.2.6/STT.exe"),
            "v0.2.7"
        ));
    }
    #[test]
    fn operations_are_exclusive_and_release_on_error() {
        let state = PendingUpdate::default();
        let operation = begin(&state).unwrap();
        assert!(begin(&state).is_err());
        drop(operation);
        assert!(begin(&state).is_ok());
    }
}
