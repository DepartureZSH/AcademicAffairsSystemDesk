from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> tuple[str, int]:
    sha256 = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha256.update(chunk)
            size += len(chunk)
    return sha256.hexdigest().upper(), size


def artifact_record(path: Path, require_signature: bool) -> dict:
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.suffix.lower() not in {".exe", ".msi"}:
        raise ValueError(f"发布制品必须是存在的 EXE/MSI: {resolved}")
    sha256, size = digest(resolved)
    signature = Path(f"{resolved}.sig")
    if require_signature and not signature.is_file():
        raise ValueError(f"发布制品缺少 updater 签名: {signature}")
    record = {
        "fileName": resolved.name,
        "sizeBytes": size,
        "sha256": sha256,
        "authenticodeExpected": True,
        "updaterSignature": None,
    }
    if signature.is_file():
        signature_sha256, signature_size = digest(signature)
        record["updaterSignature"] = {
            "fileName": signature.name,
            "sizeBytes": signature_size,
            "sha256": signature_sha256,
        }
    return record


def repository_commit(revision: str | None = None) -> str:
    requested = revision or "HEAD"
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{requested}^{{commit}}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def evidence_record(path: Path) -> dict:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"发布证据文件不存在: {resolved}")
    sha256, size = digest(resolved)
    return {"fileName": resolved.name, "sizeBytes": size, "sha256": sha256}


def checksum_records(payload: dict) -> list[dict]:
    records: list[dict] = []
    for artifact in payload["artifacts"]:
        records.append(artifact)
        if artifact.get("updaterSignature"):
            records.append(artifact["updaterSignature"])
    records.extend(payload["complianceEvidence"])
    records.extend(payload["additionalEvidence"])
    names = [record["fileName"] for record in records]
    if len(names) != len(set(names)):
        raise ValueError("发布制品或证据文件名重复")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate signed Windows release evidence")
    parser.add_argument("--artifact", action="append", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "release" / "windows-release-manifest.json",
    )
    parser.add_argument("--authenticode-thumbprint", required=True)
    parser.add_argument("--require-updater-signature", action="store_true")
    parser.add_argument(
        "--source-commit",
        help="构建二进制所使用的 Git commit；默认使用当前 HEAD",
    )
    parser.add_argument(
        "--additional-evidence",
        action="append",
        type=Path,
        default=[],
        help="加入 manifest 和 SHA256SUMS 的公开证据文件，例如测试 CER",
    )
    args = parser.parse_args()

    tauri = json.loads(
        (ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    evidence = []
    for name in ("dependency-inventory.json", "dependency-sbom.cdx.json"):
        path = ROOT / "build" / "compliance" / name
        if path.is_file():
            sha256, size = digest(path)
            evidence.append({"fileName": name, "sizeBytes": size, "sha256": sha256})

    payload = {
        "format": "tech.karios.windows-release/v1",
        "createdAt": datetime.now(UTC).isoformat(),
        "application": {
            "name": tauri["productName"],
            "identifier": tauri["identifier"],
            "version": tauri["version"],
            "target": "windows-x86_64",
        },
        "source": {
            "repository": "https://github.com/DepartureZSH/AcademicAffairsSystemDesk",
            "commit": repository_commit(args.source_commit),
        },
        "signing": {
            "authenticodeThumbprint": args.authenticode_thumbprint.replace(" ", "").upper(),
            "authenticodeProfile": "self-signed-test",
            "updaterAlgorithm": "Ed25519/minisign",
            "order": ["Authenticode", "Tauri updater signature"],
        },
        "artifacts": [
            artifact_record(path, args.require_updater_signature)
            for path in args.artifact
        ],
        "complianceEvidence": evidence,
        "additionalEvidence": [
            evidence_record(path) for path in args.additional_evidence
        ],
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksums = output.with_name("SHA256SUMS.txt")
    lines = [
        f'{item["sha256"]}  {item["fileName"]}'
        for item in checksum_records(payload)
    ]
    checksums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"release manifest: {output}")
    print(f"checksums: {checksums}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
