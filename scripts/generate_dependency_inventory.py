from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "compliance" / "dependency-inventory.json"


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
    packages = python_packages() + npm_packages() + cargo_packages()
    missing = [f'{item["ecosystem"]}:{item["name"]}@{item["version"]}' for item in packages if not item["license"]]
    payload = {
        "format": "tech.karios.dependency-inventory/v1",
        "packageCount": len(packages),
        "packages": packages,
        "missingLicenseMetadata": missing,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"dependency inventory: {OUTPUT} ({len(packages)} packages)")
    if missing:
        print("missing license metadata:")
        for item in missing:
            print(f"- {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
