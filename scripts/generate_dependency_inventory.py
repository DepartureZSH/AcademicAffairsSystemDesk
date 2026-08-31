from __future__ import annotations

import importlib.metadata
import hashlib
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "compliance" / "dependency-inventory.json"
CYCLONEDX_OUTPUT = ROOT / "build" / "compliance" / "dependency-sbom.cdx.json"
FONT_PATH = ROOT / "sidecar" / "stt_desktop" / "assets" / "fonts" / "NotoSansSC-VF.ttf"
FONT_SHA256 = "D68BAFCB48A2707749396AA12BBBD833CB70401F3A9A689FD2902C7E0D295964"
FONT_SIZE = 17_773_132


def bundled_assets() -> list[dict[str, object]]:
    if not FONT_PATH.is_file():
        raise FileNotFoundError("缺少受审计的 Noto Sans SC 字体")
    digest = hashlib.sha256(FONT_PATH.read_bytes()).hexdigest().upper()
    size = FONT_PATH.stat().st_size
    if digest != FONT_SHA256 or size != FONT_SIZE:
        raise ValueError("Noto Sans SC 字体大小或 SHA-256 与受审计来源不符")
    return [
        {
            "ecosystem": "asset",
            "name": "Noto Sans SC Variable",
            "version": "2.004",
            "license": "OFL-1.1",
            "source": "https://github.com/notofonts/noto-cjk/tree/523d033d6cb47f4a80c58a35753646f5c3608a78/Sans/Variable/TTF/Subset",
            "sha256": FONT_SHA256,
            "sizeBytes": FONT_SIZE,
        }
    ]


def python_packages() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name or name == "karios-stt-desktop":
            continue
        license_expression = distribution.metadata.get("License-Expression")
        classifiers = distribution.metadata.get_all("Classifier") or []
        classified = [item.removeprefix("License :: ") for item in classifiers if item.startswith("License :: ")]
        license_name = license_expression or distribution.metadata.get("License") or "; ".join(classified)
        records.append(
            {
                "ecosystem": "python",
                "name": name,
                "version": distribution.version,
                "license": (license_name or "").strip(),
                "source": distribution.metadata.get("Home-page") or "",
            }
        )
    return sorted(records, key=lambda item: item["name"].lower())


def npm_packages() -> list[dict[str, str]]:
    lock = json.loads((ROOT / "apps" / "desktop" / "package-lock.json").read_text(encoding="utf-8"))
    records = []
    for path, package in lock.get("packages", {}).items():
        if not path or package.get("dev"):
            continue
        name = package.get("name") or path.rsplit("node_modules/", 1)[-1]
        records.append(
            {
                "ecosystem": "npm",
                "name": name,
                "version": package.get("version", ""),
                "license": package.get("license", ""),
                "source": package.get("resolved", ""),
            }
        )
    return sorted(records, key=lambda item: item["name"].lower())


def cargo_packages() -> list[dict[str, str]]:
    cargo = Path(os.environ.get("USERPROFILE", "")) / ".cargo" / "bin" / "cargo.exe"
    command = str(cargo) if cargo.is_file() else "cargo"
    metadata = subprocess.run(
        [command, "metadata", "--format-version", "1", "--locked"],
        cwd=ROOT / "apps" / "desktop" / "src-tauri",
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    records = []
    for package in json.loads(metadata.stdout)["packages"]:
        if package.get("source") is None:
            continue
        records.append(
            {
                "ecosystem": "cargo",
                "name": package["name"],
                "version": package["version"],
                "license": package.get("license") or "",
                "source": package.get("repository") or package.get("source") or "",
            }
        )
    return sorted(records, key=lambda item: item["name"].lower())


def main() -> int:
    packages = python_packages() + npm_packages() + cargo_packages() + bundled_assets()
    missing = [f'{item["ecosystem"]}:{item["name"]}@{item["version"]}' for item in packages if not item["license"]]
    payload = {
        "format": "tech.karios.dependency-inventory/v1",
        "packageCount": len(packages),
        "packages": packages,
        "missingLicenseMetadata": missing,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    components = []
    purl_types = {"python": "pypi", "npm": "npm", "cargo": "cargo"}
    for item in packages:
        component = {
            "type": "file" if item["ecosystem"] == "asset" else "library",
            "bom-ref": f'{item["ecosystem"]}:{item["name"]}@{item["version"]}',
            "name": item["name"],
            "version": item["version"],
            "licenses": [{"license": {"name": item["license"]}}],
            "properties": [
                {"name": "tech.karios.ecosystem", "value": item["ecosystem"]}
            ],
        }
        if item["ecosystem"] == "asset":
            component["hashes"] = [{"alg": "SHA-256", "content": item["sha256"]}]
            component["properties"].append(
                {"name": "tech.karios.sizeBytes", "value": str(item["sizeBytes"])}
            )
        else:
            component["purl"] = (
                f'pkg:{purl_types[item["ecosystem"]]}/{item["name"]}@{item["version"]}'
            )
        if item["source"]:
            component["externalReferences"] = [
                {"type": "distribution", "url": item["source"]}
            ]
        components.append(component)
    tauri_config = json.loads(
        (ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    application_version = tauri_config["version"]
    cyclonedx = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": f"pkg:generic/tech.karios.stt.desktop@{application_version}",
                "name": "时奕教务排课",
                "version": application_version,
            }
        },
        "components": components,
    }
    CYCLONEDX_OUTPUT.write_text(
        json.dumps(cyclonedx, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"dependency inventory: {OUTPUT} ({len(packages)} packages)")
    print(f"CycloneDX SBOM: {CYCLONEDX_OUTPUT}")
    if missing:
        print("missing license metadata:")
        for item in missing:
            print(f"- {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
