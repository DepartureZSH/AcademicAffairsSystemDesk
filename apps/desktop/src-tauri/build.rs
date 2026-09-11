use base64::Engine;

fn main() {
    println!("cargo:rerun-if-env-changed=STT_SUPABASE_PUBLISHABLE_KEY");
    let key = std::env::var("STT_SUPABASE_PUBLISHABLE_KEY").ok();
    if std::env::var("PROFILE").as_deref() == Ok("release") && key.is_none() {
        panic!("Release login configuration is missing. Use scripts/build-windows.ps1 with a public client key.");
    }
    if let Some(key) = key {
        let key = key.trim();
        let valid_publishable = key.strip_prefix("sb_publishable_").is_some_and(|suffix| {
            !suffix.is_empty()
                && suffix
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
        });
        let parts: Vec<_> = key.split('.').collect();
        let valid_anon = parts.len() == 3
            && base64::engine::general_purpose::URL_SAFE_NO_PAD
                .decode(parts[1])
                .ok()
                .and_then(|bytes| serde_json::from_slice::<serde_json::Value>(&bytes).ok())
                .is_some_and(|claims| claims.get("role").and_then(|v| v.as_str()) == Some("anon"));
        assert!(valid_publishable || valid_anon, "Only a publishable or legacy anon client key may be bundled; secret and service-role keys are forbidden.");
    }
    tauri_build::build()
}
