use parking_lot::Mutex;
use reqwest::{Client, StatusCode};
use serde::Deserialize;
use std::net::IpAddr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

static GENERATION: AtomicU64 = AtomicU64::new(0);
static ACCESS: Mutex<Option<OnlineGrant>> = Mutex::new(None);

struct OnlineGrant {
    user_id: String,
    endpoint: String,
    expires_at: i64,
    checked: Instant,
    ttl: Duration,
}

#[derive(Deserialize)]
struct MembershipResponse {
    user_id: String,
    allowed: bool,
    reason: String,
    mode: String,
    expires_at: Option<i64>,
    checked_at: i64,
    recheck_after_seconds: u64,
}

pub fn validate_endpoint(endpoint: &str) -> Result<(), String> {
    let url = reqwest::Url::parse(endpoint).map_err(|_| "会员服务地址格式无效")?;
    let local = url.host_str().is_some_and(|host| {
        host == "localhost" || host.parse::<IpAddr>().is_ok_and(|ip| ip.is_loopback())
    });
    if (url.scheme() != "https" && !(url.scheme() == "http" && local))
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
        || url.path() != "/"
    {
        return Err("会员服务须使用 HTTPS 根地址，仅本机联调允许 HTTP".into());
    }
    Ok(())
}

pub fn clear() {
    let mut cache = ACCESS.lock();
    GENERATION.fetch_add(1, Ordering::SeqCst);
    *cache = None;
}

fn valid_grant(grant: &OnlineGrant, endpoint: &str, user: &str) -> bool {
    grant.user_id == user && grant.endpoint == endpoint && grant.checked.elapsed() < grant.ttl
}

pub fn cached_expiry(endpoint: &str, user: &str) -> Option<i64> {
    ACCESS
        .lock()
        .as_ref()
        .filter(|grant| valid_grant(grant, endpoint, user))
        .map(|grant| grant.expires_at)
}

fn validate_membership(reply: &MembershipResponse, user: &str) -> Result<(i64, Duration), String> {
    if reply.user_id != user || reply.mode != "online" {
        return Err("会员服务返回了不匹配的账号或授权模式".into());
    }
    if !reply.allowed {
        return Err(match reply.reason.as_str() {
            "email_unverified" => "请先验证账号邮箱，再重新检查会员权益",
            "membership_required" => "当前账号没有有效会员，请使用已开通会员的账号登录",
            _ => "当前账号无桌面使用权限",
        }
        .into());
    }
    let expires = reply.expires_at.ok_or("会员服务未返回有效期限")?;
    if expires <= reply.checked_at || reply.reason != "active" || reply.recheck_after_seconds == 0 {
        return Err("会员权益已过期或返回数据无效".into());
    }
    let remaining = (expires - reply.checked_at) as u64;
    Ok((
        expires,
        Duration::from_secs(reply.recheck_after_seconds.min(60).min(remaining)),
    ))
}

pub async fn check(endpoint: &str, user: &str, access_token: &str) -> Result<i64, String> {
    validate_endpoint(endpoint)?;
    let generation = GENERATION.fetch_add(1, Ordering::SeqCst) + 1;
    let started = Instant::now();
    let result = async {
        let client = Client::builder()
            .connect_timeout(Duration::from_secs(3))
            .timeout(Duration::from_secs(5))
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|_| "无法初始化会员校验服务")?;
        let response = client
            .get(format!(
                "{}/api/me/desktop-entitlement",
                endpoint.trim_end_matches('/')
            ))
            .bearer_auth(access_token)
            .send()
            .await
            .map_err(|_| "无法连接会员服务，请检查网络后重试；当前版本不支持离线授权")?;
        if !response.status().is_success() {
            return Err(match response.status() {
                StatusCode::UNAUTHORIZED => "登录会话无效，请退出后重新登录",
                StatusCode::FORBIDDEN => "当前账号无桌面使用权限",
                StatusCode::NOT_FOUND => "会员服务尚未更新，请先部署新版 stt-api",
                _ => "会员服务暂时不可用，请稍后重试",
            }
            .into());
        }
        let reply = response
            .json::<MembershipResponse>()
            .await
            .map_err(|_| "会员服务返回格式无效")?;
        validate_membership(&reply, user)
    }
    .await;
    let mut cache = ACCESS.lock();
    if GENERATION.load(Ordering::SeqCst) != generation {
        return Err("账号会话已变化，请重新检查会员权益".into());
    }
    match result {
        Ok((expires_at, ttl)) if started.elapsed() < ttl => {
            *cache = Some(OnlineGrant {
                user_id: user.into(),
                endpoint: endpoint.into(),
                expires_at,
                checked: started,
                ttl,
            });
            Ok(expires_at)
        }
        result => {
            *cache = None;
            Err(result
                .err()
                .unwrap_or_else(|| "会员权益已过期，请重新检查".into()))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};

    fn test_server(body: String, status: &str) -> String {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let status = status.to_owned();
        std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            let mut buffer = [0; 4096];
            let count = stream.read(&mut buffer).unwrap();
            let request = String::from_utf8_lossy(&buffer[..count]).to_lowercase();
            assert!(request.contains("get /api/me/desktop-entitlement "));
            assert!(request.contains("authorization: bearer test-token"));
            let response = format!("HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len());
            stream.write_all(response.as_bytes()).unwrap();
        });
        endpoint
    }

    #[test]
    fn actual_http_checks_and_denials_clear_previous_permission() {
        tauri::async_runtime::block_on(async {
            let valid = r#"{"user_id":"user","allowed":true,"reason":"active","mode":"online","expires_at":1000,"checked_at":900,"recheck_after_seconds":60}"#;
            let endpoint = test_server(valid.into(), "200 OK");
            assert_eq!(check(&endpoint, "user", "test-token").await.unwrap(), 1000);
            assert_eq!(cached_expiry(&endpoint, "user"), Some(1000));
            assert_eq!(cached_expiry(&endpoint, "other"), None);
            let unavailable = test_server("{}".into(), "503 Service Unavailable");
            assert!(check(&unavailable, "user", "test-token").await.is_err());
            assert_eq!(cached_expiry(&endpoint, "user"), None);
            let foreign = test_server(valid.into(), "200 OK");
            assert!(check(&foreign, "other", "test-token").await.is_err());
            let malformed = test_server("{}".into(), "200 OK");
            assert!(check(&malformed, "user", "test-token").await.is_err());
            let endpoint = test_server(valid.into(), "200 OK");
            assert!(check(&endpoint, "user", "test-token").await.is_ok());
            clear();
            assert_eq!(cached_expiry(&endpoint, "user"), None);
        });
    }

    fn reply() -> MembershipResponse {
        MembershipResponse {
            user_id: "user".into(),
            allowed: true,
            reason: "active".into(),
            mode: "online".into(),
            expires_at: Some(1000),
            checked_at: 900,
            recheck_after_seconds: 60,
        }
    }

    #[test]
    fn membership_checks_identity_expiry_and_explicit_permission() {
        assert!(validate_membership(&reply(), "user").is_ok());
        assert!(validate_membership(&reply(), "other").is_err());
        let mut response = reply();
        response.expires_at = Some(900);
        assert!(validate_membership(&response, "user").is_err());
        response = reply();
        response.allowed = false;
        assert!(validate_membership(&response, "user").is_err());
        response = reply();
        response.mode = "mock".into();
        assert!(validate_membership(&response, "user").is_err());
    }

    #[test]
    fn cache_is_ephemeral_bounded_and_account_scoped() {
        let grant = OnlineGrant {
            user_id: "user".into(),
            endpoint: "https://api.example".into(),
            expires_at: 1000,
            checked: Instant::now(),
            ttl: Duration::from_secs(60),
        };
        assert!(valid_grant(&grant, "https://api.example", "user"));
        assert!(!valid_grant(&grant, "https://api.example", "other"));
        assert!(!valid_grant(&grant, "https://other.example", "user"));
        let expired = OnlineGrant {
            ttl: Duration::ZERO,
            ..grant
        };
        assert!(!valid_grant(&expired, "https://api.example", "user"));
    }

    #[test]
    fn server_cannot_expand_online_cache_or_member_expiry() {
        let mut response = reply();
        response.recheck_after_seconds = 604800;
        assert_eq!(
            validate_membership(&response, "user").unwrap().1,
            Duration::from_secs(60)
        );
        response.expires_at = Some(902);
        assert_eq!(
            validate_membership(&response, "user").unwrap().1,
            Duration::from_secs(2)
        );
    }

    #[test]
    fn endpoints_do_not_allow_remote_http_or_embedded_credentials() {
        assert!(validate_endpoint("https://fjozndbjkinl.sealosbja.site").is_ok());
        assert!(validate_endpoint("http://127.0.0.1:8000").is_ok());
        for url in [
            "http://remote.example",
            "https://user:secret@example.com",
            "https://example.com/path",
            "https://example.com?token=secret",
        ] {
            assert!(validate_endpoint(url).is_err());
        }
    }
}
