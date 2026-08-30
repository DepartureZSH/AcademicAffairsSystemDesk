use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use minisign_verify::{PublicKey, Signature};
use serde_json::Value;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut arguments = std::env::args_os().skip(1);
    let artifact = PathBuf::from(arguments.next().ok_or("缺少安装包路径")?);
    let signature_path = PathBuf::from(arguments.next().ok_or("缺少 .sig 路径")?);
    let config_path = arguments
        .next()
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("tauri.conf.json"));

    let config: Value = serde_json::from_slice(&std::fs::read(config_path)?)?;
    let encoded_public_key = config["plugins"]["updater"]["pubkey"]
        .as_str()
        .ok_or("tauri.conf.json 缺少 updater.pubkey")?;
    let public_key_text = String::from_utf8(BASE64.decode(encoded_public_key.trim())?)?;
    let encoded_signature = std::fs::read_to_string(signature_path)?;
    let signature_text = String::from_utf8(BASE64.decode(encoded_signature.trim())?)?;
    let public_key = PublicKey::decode(&public_key_text)?;
    let signature = Signature::decode(&signature_text)?;
    let content = std::fs::read(&artifact)?;
    public_key.verify(&content, &signature, false)?;

    println!(
        "updater signature verified: {} ({} bytes)",
        artifact.display(),
        content.len()
    );
    Ok(())
}
