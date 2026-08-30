use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use keyring::{Entry, Error as KeyringError};
use rand::RngCore;
use reqwest::{Client, StatusCode};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::net::IpAddr;
use std::path::Path;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use subtle::ConstantTimeEq;

const CREDENTIAL_SERVICE: &str = "tech.karios.stt.desktop";
const SESSION_CREDENTIAL: &str = "supabase-session";
const DEVICE_CREDENTIAL: &str = "device-ed25519";
const ENTITLEMENT_CREDENTIAL: &str = "mock-entitlement";
const CLOCK_CREDENTIAL: &str = "license-clock-checkpoint";
const REFRESH_MARGIN_SECONDS: i64 = 60;
const CLOCK_ROLLBACK_TOLERANCE_SECONDS: i64 = 300;
const IDENTITY_CONNECT_TIMEOUT: Duration = Duration::from_secs(3);
const IDENTITY_REQUEST_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Clone, Debug, Deserialize)]
struct RawConfig {
    services: HashMap<String, RawService>,
}

#[derive(Clone, Debug, Deserialize)]
struct RawService {
    mode: String,
    endpoint: Option<String>,
    #[serde(default)]
    env: HashMap<String, String>,
    #[serde(default)]
    mock: HashMap<String, Value>,
}

#[derive(Clone, Debug)]
struct IdentityConfig {
    endpoint: String,
    publishable_key: String,
}

#[derive(Clone, Debug)]
struct LicenseConfig {
    mode: String,
    activation_code: Option<String>,
    expires_in_seconds: i64,
    device_limit: u32,
    revoked: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AuthUser {
    pub id: String,
    pub email: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct StoredSession {
    access_token: String,
    refresh_token: String,
    expires_at: i64,
    user: AuthUser,
}

#[derive(Clone, Debug, Deserialize)]
struct SupabaseUser {
    id: String,
    email: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
struct SupabaseSessionResponse {
    access_token: String,
    refresh_token: String,
    expires_in: i64,
    user: SupabaseUser,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AuthStatus {
    pub configured: bool,
    pub authenticated: bool,
    pub offline: bool,
    pub user: Option<AuthUser>,
    pub message: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct EntitlementClaims {
    version: u32,
    mode: String,
    account_id: String,
    device_id: String,
    issued_at: i64,
    expires_at: i64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct EntitlementEnvelope {
    claims: EntitlementClaims,
    signature: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LicenseStatus {
    pub mode: String,
    pub active: bool,
    pub needs_activation: bool,
    pub expires_at: Option<i64>,
    pub device_id: Option<String>,
    pub device_limit: u32,
    pub message: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GateStatus {
    pub auth: AuthStatus,
    pub license: LicenseStatus,
    pub can_start_sidecar: bool,
}

fn now_seconds() -> Result<i64, String> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .map_err(|_| "系统时间早于 UNIX epoch，需要联网校验".into())
}

fn clock_is_acceptable(now: i64, last_seen: Option<i64>) -> bool {
    last_seen
        .is_none_or(|checkpoint| now.saturating_add(CLOCK_ROLLBACK_TOLERANCE_SECONDS) >= checkpoint)
}

fn check_and_advance_clock(now: i64) -> Result<bool, String> {
    let checkpoint = read_credential(CLOCK_CREDENTIAL)?
        .map(|value| {
            value
                .parse::<i64>()
                .map_err(|_| "本地授权时钟检查点已损坏".to_string())
        })
        .transpose()?;
    if !clock_is_acceptable(now, checkpoint) {
        return Ok(false);
    }
    if checkpoint.is_none_or(|value| now > value) {
        write_credential(CLOCK_CREDENTIAL, &now.to_string())?;
    }
    Ok(true)
}

fn reset_clock_checkpoint(now: i64) -> Result<(), String> {
    write_credential(CLOCK_CREDENTIAL, &now.to_string())
}

fn load_config(root: &Path) -> Result<RawConfig, String> {
    let path = root.join("config/services.yaml");
    let content = std::fs::read_to_string(path).map_err(|_| "无法读取服务配置".to_string())?;
    serde_yaml::from_str(&content).map_err(|_| "服务配置格式无效".to_string())
}

fn service<'a>(config: &'a RawConfig, name: &str) -> Result<&'a RawService, String> {
    config
        .services
        .get(name)
        .ok_or_else(|| format!("服务配置缺少 {name}"))
}

fn identity_config(root: &Path) -> Result<IdentityConfig, String> {
    let config = load_config(root)?;
    let identity = service(&config, "identity")?;
    if identity.mode != "real" {
        return Err("当前桌面身份模块只允许 real Supabase Auth".into());
    }
    let endpoint = identity
        .endpoint
        .clone()
        .ok_or("Supabase 身份服务缺少 endpoint")?;
    let parsed = reqwest::Url::parse(&endpoint).map_err(|_| "Supabase endpoint 格式无效")?;
    let loopback = parsed.host_str().is_some_and(|host| {
        host.eq_ignore_ascii_case("localhost")
            || host
                .parse::<IpAddr>()
                .map(|address| address.is_loopback())
                .unwrap_or(false)
    });
    if parsed.scheme() != "https" && !(parsed.scheme() == "http" && loopback) {
        return Err("Supabase 身份服务必须使用 HTTPS；仅本机回环开发环境可使用 HTTP".into());
    }
    let variable = identity
        .env
        .get("publishable_key")
        .ok_or("Supabase 身份服务缺少 publishable_key 环境变量引用")?;
    let publishable_key =
        std::env::var(variable).map_err(|_| format!("尚未配置环境变量 {variable}"))?;
    if publishable_key.trim().is_empty() {
        return Err(format!("环境变量 {variable} 为空"));
    }
    Ok(IdentityConfig {
        endpoint: endpoint.trim_end_matches('/').into(),
        publishable_key,
    })
}

fn license_config(root: &Path) -> Result<LicenseConfig, String> {
    let config = load_config(root)?;
    let license = service(&config, "license")?;
    let expires_in_seconds = license
        .mock
        .get("expires_in_seconds")
        .and_then(Value::as_i64)
        .unwrap_or(604_800);
    let device_limit = license
        .mock
        .get("device_limit")
        .and_then(Value::as_u64)
        .unwrap_or(3) as u32;
    let revoked = license
        .mock
        .get("revoked")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let activation_code = license
        .mock
        .get("activation_code")
        .and_then(Value::as_str)
        .map(str::to_owned);
    Ok(LicenseConfig {
        mode: license.mode.clone(),
        activation_code,
        expires_in_seconds,
        device_limit,
        revoked,
    })
}

fn entry(name: &str) -> Result<Entry, String> {
    Entry::new(CREDENTIAL_SERVICE, name).map_err(|_| "系统凭据存储不可用".into())
}

fn read_credential(name: &str) -> Result<Option<String>, String> {
    match entry(name)?.get_password() {
        Ok(value) => Ok(Some(value)),
        Err(KeyringError::NoEntry) => Ok(None),
        Err(_) => Err("读取系统凭据失败".into()),
    }
}

fn write_credential(name: &str, value: &str) -> Result<(), String> {
    entry(name)?
        .set_password(value)
        .map_err(|_| "写入系统凭据失败".into())
}

fn delete_credential(name: &str) -> Result<(), String> {
    match entry(name)?.delete_credential() {
        Ok(()) | Err(KeyringError::NoEntry) => Ok(()),
        Err(_) => Err("清除系统凭据失败".into()),
    }
}

fn load_session() -> Result<Option<StoredSession>, String> {
    read_credential(SESSION_CREDENTIAL)?
        .map(|value| serde_json::from_str(&value).map_err(|_| "本地登录会话已损坏".into()))
        .transpose()
}

fn store_session(response: SupabaseSessionResponse) -> Result<StoredSession, String> {
    let email = response.user.email.ok_or("Supabase 用户缺少邮箱")?;
    let session = StoredSession {
        access_token: response.access_token,
        refresh_token: response.refresh_token,
        expires_at: now_seconds()? + response.expires_in.max(1),
        user: AuthUser {
            id: response.user.id,
            email,
        },
    };
    let serialized = serde_json::to_string(&session).map_err(|_| "无法保存登录会话")?;
    write_credential(SESSION_CREDENTIAL, &serialized)?;
    Ok(session)
}

fn auth_status_for(
    session: Option<&StoredSession>,
    offline: bool,
    message: Option<String>,
) -> AuthStatus {
    AuthStatus {
        configured: true,
        authenticated: session.is_some(),
        offline,
        user: session.map(|item| item.user.clone()),
        message,
    }
}

fn supabase_headers(
    request: reqwest::RequestBuilder,
    config: &IdentityConfig,
) -> reqwest::RequestBuilder {
    request
        .header("apikey", &config.publishable_key)
        .header("Content-Type", "application/json")
}

fn identity_client() -> Result<Client, String> {
    Client::builder()
        .connect_timeout(IDENTITY_CONNECT_TIMEOUT)
        .timeout(IDENTITY_REQUEST_TIMEOUT)
        .build()
        .map_err(|_| "无法初始化身份服务客户端".into())
}

fn safe_auth_error(status: StatusCode) -> String {
    match status {
        StatusCode::BAD_REQUEST => "邮箱、密码或请求格式无效".into(),
        StatusCode::UNAUTHORIZED => "邮箱或密码错误，或邮箱尚未验证".into(),
        StatusCode::TOO_MANY_REQUESTS => "尝试次数过多，请稍后再试".into(),
        _ if status.is_server_error() => "身份服务暂时不可用".into(),
        _ => "身份请求未成功".into(),
    }
}

fn recovery_token(config: &IdentityConfig, recovery_link: &str) -> Result<String, String> {
    let trimmed = recovery_link.trim();
    if trimmed.is_empty() || trimmed.len() > 8_192 {
        return Err("密码恢复链接为空或过长".into());
    }
    let endpoint = reqwest::Url::parse(&config.endpoint)
        .map_err(|_| "Supabase endpoint 格式无效".to_string())?;
    let link = reqwest::Url::parse(trimmed).map_err(|_| "密码恢复链接格式无效".to_string())?;
    let same_origin = link.scheme() == endpoint.scheme()
        && link.host_str() == endpoint.host_str()
        && link.port_or_known_default() == endpoint.port_or_known_default();
    if !same_origin || !link.username().is_empty() || link.password().is_some() {
        return Err("密码恢复链接不属于当前身份服务".into());
    }
    if link.path() != "/auth/v1/verify" || link.fragment().is_some() {
        return Err("密码恢复链接路径无效".into());
    }
    let mut token: Option<String> = None;
    let mut recovery_type: Option<String> = None;
    for (key, value) in link.query_pairs() {
        match key.as_ref() {
            "token" | "token_hash" => {
                if token.replace(value.into_owned()).is_some() {
                    return Err("密码恢复链接包含重复 token".into());
                }
            }
            "type" => {
                if recovery_type.replace(value.into_owned()).is_some() {
                    return Err("密码恢复链接包含重复 type".into());
                }
            }
            _ => {}
        }
    }
    if recovery_type.as_deref() != Some("recovery") {
        return Err("该链接不是密码恢复链接".into());
    }
    let token = token.ok_or("密码恢复链接缺少 token")?;
    if token.len() < 16 || token.len() > 4_096 {
        return Err("密码恢复 token 长度无效".into());
    }
    Ok(token)
}

async fn refresh_session(
    client: &Client,
    config: &IdentityConfig,
    session: &StoredSession,
) -> Result<StoredSession, String> {
    let response = supabase_headers(
        client.post(format!(
            "{}/auth/v1/token?grant_type=refresh_token",
            config.endpoint
        )),
        config,
    )
    .json(&json!({"refresh_token": session.refresh_token}))
    .send()
    .await
    .map_err(|_| "身份服务网络不可用".to_string())?;
    if !response.status().is_success() {
        return Err(safe_auth_error(response.status()));
    }
    let payload = response
        .json::<SupabaseSessionResponse>()
        .await
        .map_err(|_| "身份服务返回格式无效".to_string())?;
    store_session(payload)
}

async fn current_auth_status(root: &Path) -> Result<AuthStatus, String> {
    let config = match identity_config(root) {
        Ok(config) => config,
        Err(message) => {
            return Ok(AuthStatus {
                configured: false,
                authenticated: false,
                offline: false,
                user: None,
                message: Some(message),
            })
        }
    };
    let Some(session) = load_session()? else {
        return Ok(auth_status_for(None, false, None));
    };
    if session.expires_at > now_seconds()? + REFRESH_MARGIN_SECONDS {
        return Ok(auth_status_for(Some(&session), false, None));
    }
    match refresh_session(&identity_client()?, &config, &session).await {
        Ok(refreshed) => Ok(auth_status_for(Some(&refreshed), false, None)),
        Err(_) => Ok(auth_status_for(
            Some(&session),
            true,
            Some("当前离线，将使用尚未到期的设备授权".into()),
        )),
    }
}

fn device_signing_key() -> Result<SigningKey, String> {
    if let Some(encoded) = read_credential(DEVICE_CREDENTIAL)? {
        let bytes = BASE64
            .decode(encoded)
            .map_err(|_| "设备私钥格式无效".to_string())?;
        let secret: [u8; 32] = bytes
            .try_into()
            .map_err(|_| "设备私钥长度无效".to_string())?;
        return Ok(SigningKey::from_bytes(&secret));
    }
    let mut secret = [0_u8; 32];
    rand::rng().fill_bytes(&mut secret);
    write_credential(DEVICE_CREDENTIAL, &BASE64.encode(secret))?;
    Ok(SigningKey::from_bytes(&secret))
}

fn device_id(key: &SigningKey) -> String {
    let digest = Sha256::digest(key.verifying_key().as_bytes());
    hex::encode(&digest[..16])
}

fn sign_claims(key: &SigningKey, claims: EntitlementClaims) -> Result<EntitlementEnvelope, String> {
    let payload = serde_json::to_vec(&claims).map_err(|_| "无法生成本地授权")?;
    let signature = key.sign(&payload);
    Ok(EntitlementEnvelope {
        claims,
        signature: BASE64.encode(signature.to_bytes()),
    })
}

fn activation_code_matches(expected: &str, supplied: &str) -> bool {
    let expected_digest = Sha256::digest(expected.as_bytes());
    let supplied_digest = Sha256::digest(supplied.trim().as_bytes());
    bool::from(expected_digest.ct_eq(&supplied_digest))
}

fn verify_envelope(key: &SigningKey, envelope: &EntitlementEnvelope) -> Result<(), String> {
    let payload = serde_json::to_vec(&envelope.claims).map_err(|_| "本地授权格式无效")?;
    let bytes = BASE64
        .decode(&envelope.signature)
        .map_err(|_| "本地授权签名格式无效".to_string())?;
    let signature_bytes: [u8; 64] = bytes
        .try_into()
        .map_err(|_| "本地授权签名长度无效".to_string())?;
    let signature = Signature::from_bytes(&signature_bytes);
    let verifying_key =
        VerifyingKey::from_bytes(key.verifying_key().as_bytes()).map_err(|_| "设备公钥无效")?;
    verifying_key
        .verify(&payload, &signature)
        .map_err(|_| "本地授权已被篡改".into())
}

fn read_entitlement() -> Result<Option<EntitlementEnvelope>, String> {
    read_credential(ENTITLEMENT_CREDENTIAL)?
        .map(|value| serde_json::from_str(&value).map_err(|_| "本地授权格式无效".into()))
        .transpose()
}

fn current_license_status(root: &Path, auth: &AuthStatus) -> Result<LicenseStatus, String> {
    let config = license_config(root)?;
    if !auth.authenticated {
        return Ok(LicenseStatus {
            mode: config.mode,
            active: false,
            needs_activation: false,
            expires_at: None,
            device_id: None,
            device_limit: config.device_limit,
            message: Some("请先登录 Supabase 账号".into()),
        });
    }
    if config.mode != "mock" {
        return Ok(LicenseStatus {
            mode: config.mode,
            active: false,
            needs_activation: true,
            expires_at: None,
            device_id: None,
            device_limit: config.device_limit,
            message: Some("真实许可证接口尚未接入".into()),
        });
    }
    if config.revoked {
        return Ok(LicenseStatus {
            mode: config.mode,
            active: false,
            needs_activation: false,
            expires_at: None,
            device_id: None,
            device_limit: config.device_limit,
            message: Some("许可证已被撤销".into()),
        });
    }
    let key = device_signing_key()?;
    let local_device_id = device_id(&key);
    let Some(envelope) = read_entitlement()? else {
        return Ok(LicenseStatus {
            mode: config.mode,
            active: false,
            needs_activation: true,
            expires_at: None,
            device_id: Some(local_device_id),
            device_limit: config.device_limit,
            message: Some("请输入企业密钥激活当前设备".into()),
        });
    };
    verify_envelope(&key, &envelope)?;
    let now = now_seconds()?;
    let clock_acceptable = check_and_advance_clock(now)?;
    let account_matches = auth
        .user
        .as_ref()
        .is_some_and(|user| user.id == envelope.claims.account_id);
    let device_matches = envelope.claims.device_id == local_device_id;
    let active = account_matches
        && device_matches
        && envelope.claims.mode == "mock"
        && envelope.claims.expires_at > now
        && clock_acceptable;
    Ok(LicenseStatus {
        mode: config.mode,
        active,
        needs_activation: !active,
        expires_at: Some(envelope.claims.expires_at),
        device_id: Some(local_device_id),
        device_limit: config.device_limit,
        message: (!active).then_some(if !clock_acceptable {
            "检测到系统时钟明显回拨，请联网校验；Mock 环境可重新输入测试企业密钥".into()
        } else {
            "授权已过期或与当前账号/设备不匹配".into()
        }),
    })
}

pub async fn status(root: &Path) -> Result<GateStatus, String> {
    let auth = current_auth_status(root).await?;
    let license = current_license_status(root, &auth)?;
    Ok(GateStatus {
        can_start_sidecar: auth.authenticated && license.active,
        auth,
        license,
    })
}

pub async fn sign_in(root: &Path, email: String, password: String) -> Result<GateStatus, String> {
    let config = identity_config(root)?;
    let response = supabase_headers(
        identity_client()?.post(format!(
            "{}/auth/v1/token?grant_type=password",
            config.endpoint
        )),
        &config,
    )
    .json(&json!({"email": email.trim(), "password": password}))
    .send()
    .await
    .map_err(|_| "无法连接身份服务".to_string())?;
    if !response.status().is_success() {
        return Err(safe_auth_error(response.status()));
    }
    let payload = response
        .json::<SupabaseSessionResponse>()
        .await
        .map_err(|_| "身份服务返回格式无效".to_string())?;
    store_session(payload)?;
    status(root).await
}

pub async fn sign_up(root: &Path, email: String, password: String) -> Result<AuthStatus, String> {
    let config = identity_config(root)?;
    let response = supabase_headers(
        identity_client()?.post(format!("{}/auth/v1/signup", config.endpoint)),
        &config,
    )
    .json(&json!({"email": email.trim(), "password": password}))
    .send()
    .await
    .map_err(|_| "无法连接身份服务".to_string())?;
    if !response.status().is_success() {
        return Err(safe_auth_error(response.status()));
    }
    let payload = response
        .json::<Value>()
        .await
        .map_err(|_| "身份服务返回格式无效".to_string())?;
    if payload.get("access_token").is_some() {
        let session: SupabaseSessionResponse =
            serde_json::from_value(payload).map_err(|_| "身份服务返回格式无效")?;
        let stored = store_session(session)?;
        return Ok(auth_status_for(Some(&stored), false, None));
    }
    Ok(AuthStatus {
        configured: true,
        authenticated: false,
        offline: false,
        user: None,
        message: Some("注册成功，请完成邮箱验证后登录".into()),
    })
}

pub async fn request_password_reset(root: &Path, email: String) -> Result<String, String> {
    let config = identity_config(root)?;
    let response = supabase_headers(
        identity_client()?.post(format!("{}/auth/v1/recover", config.endpoint)),
        &config,
    )
    .json(&json!({"email": email.trim()}))
    .send()
    .await
    .map_err(|_| "无法连接身份服务".to_string())?;
    if !response.status().is_success() {
        return Err(safe_auth_error(response.status()));
    }
    Ok("若邮箱已注册，密码重置邮件将发送到该地址".into())
}

pub async fn complete_password_reset(
    root: &Path,
    recovery_link: String,
    new_password: String,
) -> Result<String, String> {
    if new_password.len() < 8 || new_password.len() > 1_024 {
        return Err("新密码长度必须为 8–1024 个字符".into());
    }
    let config = identity_config(root)?;
    let token_hash = recovery_token(&config, &recovery_link)?;
    let client = identity_client()?;
    let verify_response = supabase_headers(
        client.post(format!("{}/auth/v1/verify", config.endpoint)),
        &config,
    )
    .json(&json!({"token_hash": token_hash, "type": "recovery"}))
    .send()
    .await
    .map_err(|_| "无法连接身份服务".to_string())?;
    if !verify_response.status().is_success() {
        return Err(safe_auth_error(verify_response.status()));
    }
    let recovery_session = verify_response
        .json::<SupabaseSessionResponse>()
        .await
        .map_err(|_| "身份服务返回格式无效".to_string())?;
    let account_id = recovery_session.user.id.clone();
    let update_response = supabase_headers(
        client
            .put(format!("{}/auth/v1/user", config.endpoint))
            .bearer_auth(&recovery_session.access_token),
        &config,
    )
    .json(&json!({"password": new_password}))
    .send()
    .await
    .map_err(|_| "无法连接身份服务".to_string())?;
    if !update_response.status().is_success() {
        return Err(safe_auth_error(update_response.status()));
    }
    let updated_user = update_response
        .json::<SupabaseUser>()
        .await
        .map_err(|_| "身份服务返回格式无效".to_string())?;
    if updated_user.id != account_id {
        return Err("身份服务返回了不匹配的账号".into());
    }
    let _ = supabase_headers(
        client
            .post(format!("{}/auth/v1/logout", config.endpoint))
            .bearer_auth(recovery_session.access_token),
        &config,
    )
    .send()
    .await;
    delete_credential(SESSION_CREDENTIAL)?;
    delete_credential(ENTITLEMENT_CREDENTIAL)?;
    Ok("密码已更新，请使用新密码登录".into())
}

pub async fn sign_out(root: &Path) -> Result<GateStatus, String> {
    if let (Ok(config), Some(session)) = (identity_config(root), load_session()?) {
        let _ = supabase_headers(
            identity_client()?
                .post(format!("{}/auth/v1/logout", config.endpoint))
                .bearer_auth(session.access_token),
            &config,
        )
        .send()
        .await;
    }
    delete_credential(SESSION_CREDENTIAL)?;
    delete_credential(ENTITLEMENT_CREDENTIAL)?;
    status(root).await
}

pub async fn activate(root: &Path, enterprise_key: String) -> Result<GateStatus, String> {
    let auth = current_auth_status(root).await?;
    let user = auth.user.as_ref().ok_or("请先登录 Supabase 账号")?;
    let config = license_config(root)?;
    if config.mode != "mock" {
        return Err("真实许可证激活接口尚未接入".into());
    }
    if config.revoked {
        return Err("许可证已被撤销".into());
    }
    let expected = config
        .activation_code
        .ok_or("Mock 许可证缺少 activation_code")?;
    if !activation_code_matches(&expected, &enterprise_key) {
        return Err("企业密钥无效".into());
    }
    let key = device_signing_key()?;
    let issued_at = now_seconds()?;
    let envelope = sign_claims(
        &key,
        EntitlementClaims {
            version: 1,
            mode: "mock".into(),
            account_id: user.id.clone(),
            device_id: device_id(&key),
            issued_at,
            expires_at: issued_at + config.expires_in_seconds.max(1),
        },
    )?;
    let serialized = serde_json::to_string(&envelope).map_err(|_| "无法保存本地授权")?;
    reset_clock_checkpoint(issued_at)?;
    write_credential(ENTITLEMENT_CREDENTIAL, &serialized)?;
    status(root).await
}

pub fn ensure_sidecar_allowed(root: &Path) -> Result<(), String> {
    let session = load_session()?.ok_or("未登录，不能启动本地算法服务")?;
    let auth = auth_status_for(Some(&session), true, None);
    let license = current_license_status(root, &auth)?;
    if license.active {
        Ok(())
    } else {
        Err(license.message.unwrap_or_else(|| "许可证无效".into()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn signing_key() -> SigningKey {
        SigningKey::from_bytes(&[7_u8; 32])
    }

    fn identity() -> IdentityConfig {
        IdentityConfig {
            endpoint: "https://auth.example.test".into(),
            publishable_key: "publishable-test-key".into(),
        }
    }

    #[test]
    fn signed_entitlement_detects_tampering() {
        let key = signing_key();
        let mut envelope = sign_claims(
            &key,
            EntitlementClaims {
                version: 1,
                mode: "mock".into(),
                account_id: "account".into(),
                device_id: device_id(&key),
                issued_at: 10,
                expires_at: 20,
            },
        )
        .unwrap();
        assert!(verify_envelope(&key, &envelope).is_ok());
        envelope.claims.account_id = "another-account".into();
        assert!(verify_envelope(&key, &envelope).is_err());
    }

    #[test]
    fn device_identifier_is_stable_and_non_secret() {
        let key = signing_key();
        assert_eq!(device_id(&key), device_id(&key));
        assert_eq!(device_id(&key).len(), 32);
        assert!(!device_id(&key).contains(&BASE64.encode(key.to_bytes())));
    }

    #[test]
    fn mock_activation_code_requires_exact_match() {
        assert!(activation_code_matches("KARIOS-MOCK", " KARIOS-MOCK "));
        assert!(!activation_code_matches("KARIOS-MOCK", "KARIOS-MOCK-OTHER"));
    }

    #[test]
    fn clock_rollback_beyond_tolerance_requires_validation() {
        assert!(clock_is_acceptable(1_000, None));
        assert!(clock_is_acceptable(1_000, Some(1_300)));
        assert!(!clock_is_acceptable(1_000, Some(1_301)));
        assert!(clock_is_acceptable(2_000, Some(1_000)));
    }

    #[test]
    fn recovery_link_requires_same_origin_path_and_type() {
        let valid = "https://auth.example.test/auth/v1/verify?token=1234567890abcdef&type=recovery&redirect_to=https%3A%2F%2Fapp.example.test";
        assert_eq!(
            recovery_token(&identity(), valid).unwrap(),
            "1234567890abcdef"
        );
        assert!(recovery_token(
            &identity(),
            "https://evil.example/auth/v1/verify?token=1234567890abcdef&type=recovery"
        )
        .is_err());
        assert!(recovery_token(
            &identity(),
            "https://auth.example.test/other?token=1234567890abcdef&type=recovery"
        )
        .is_err());
        assert!(recovery_token(
            &identity(),
            "https://auth.example.test/auth/v1/verify?token=1234567890abcdef&type=signup"
        )
        .is_err());
    }

    #[test]
    fn recovery_link_rejects_duplicate_or_short_token() {
        assert!(recovery_token(
            &identity(),
            "https://auth.example.test/auth/v1/verify?token=1234567890abcdef&token=abcdef1234567890&type=recovery"
        )
        .is_err());
        assert!(recovery_token(
            &identity(),
            "https://auth.example.test/auth/v1/verify?token=short&type=recovery"
        )
        .is_err());
    }

    #[test]
    fn identity_network_timeouts_are_bounded_for_startup() {
        assert_eq!(IDENTITY_CONNECT_TIMEOUT, Duration::from_secs(3));
        assert_eq!(IDENTITY_REQUEST_TIMEOUT, Duration::from_secs(5));
        assert!(identity_client().is_ok());
    }
}
