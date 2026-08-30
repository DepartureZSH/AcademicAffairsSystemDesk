from __future__ import annotations

import json
import importlib.util
import tomllib
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_release_manifest.py"
SPEC = importlib.util.spec_from_file_location("generate_release_manifest", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
artifact_record = MODULE.artifact_record
checksum_records = MODULE.checksum_records
digest = MODULE.digest
evidence_record = MODULE.evidence_record

INVENTORY_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "generate_dependency_inventory.py"
)
INVENTORY_SPEC = importlib.util.spec_from_file_location(
    "generate_dependency_inventory", INVENTORY_SCRIPT_PATH
)
assert INVENTORY_SPEC and INVENTORY_SPEC.loader
INVENTORY_MODULE = importlib.util.module_from_spec(INVENTORY_SPEC)
INVENTORY_SPEC.loader.exec_module(INVENTORY_MODULE)


def test_release_artifact_record_requires_installer_and_updater_signature(
    tmp_path: Path,
) -> None:
    installer = tmp_path / "时奕教务排课.exe"
    installer.write_bytes(b"signed-installer-bytes")

    with pytest.raises(ValueError, match="updater 签名"):
        artifact_record(installer, require_signature=True)

    signature = Path(f"{installer}.sig")
    signature.write_text("untrusted comment: test\n", encoding="utf-8")
    record = artifact_record(installer, require_signature=True)

    assert record["fileName"] == installer.name
    assert record["sha256"] == digest(installer)[0]
    assert record["updaterSignature"]["fileName"] == signature.name
    assert len(record["updaterSignature"]["sha256"]) == 64


def test_release_checksums_include_signatures_and_additional_evidence(
    tmp_path: Path,
) -> None:
    installer = tmp_path / "Karios-STT-Desktop.exe"
    installer.write_bytes(b"signed-installer-bytes")
    signature = Path(f"{installer}.sig")
    signature.write_bytes(b"updater-signature")
    certificate = tmp_path / "Karios-Desktop-TEST-ONLY.cer"
    certificate.write_bytes(b"public-certificate")
    payload = {
        "artifacts": [artifact_record(installer, require_signature=True)],
        "complianceEvidence": [],
        "additionalEvidence": [evidence_record(certificate)],
    }

    records = checksum_records(payload)

    assert [record["fileName"] for record in records] == [
        installer.name,
        signature.name,
        certificate.name,
    ]


def test_release_checksums_reject_duplicate_asset_names(tmp_path: Path) -> None:
    first = tmp_path / "first" / "same.json"
    second = tmp_path / "second" / "same.json"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    payload = {
        "artifacts": [],
        "complianceEvidence": [evidence_record(first)],
        "additionalEvidence": [evidence_record(second)],
    }

    with pytest.raises(ValueError, match="文件名重复"):
        checksum_records(payload)


def test_cyclonedx_sbom_has_one_component_per_inventory_package() -> None:
    root = Path(__file__).resolve().parents[1]
    inventory_path = root / "build" / "compliance" / "dependency-inventory.json"
    sbom_path = root / "build" / "compliance" / "dependency-sbom.cdx.json"
    if not inventory_path.is_file() or not sbom_path.is_file():
        pytest.skip("先运行依赖清单生成器")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert len(sbom["components"]) == inventory["packageCount"]


def test_bundled_font_matches_audited_asset_metadata() -> None:
    records = INVENTORY_MODULE.bundled_assets()

    assert records == [
        {
            "ecosystem": "asset",
            "name": "Noto Sans SC Variable",
            "version": "2.004",
            "license": "OFL-1.1",
            "source": "https://github.com/notofonts/noto-cjk/tree/523d033d6cb47f4a80c58a35753646f5c3608a78/Sans/Variable/TTF/Subset",
            "sha256": "D68BAFCB48A2707749396AA12BBBD833CB70401F3A9A689FD2902C7E0D295964",
            "sizeBytes": 17_773_132,
        }
    ]


def test_windows_installers_block_downgrades_and_keep_stable_upgrade_identity() -> None:
    root = Path(__file__).resolve().parents[1]
    config = json.loads(
        (root / "apps" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    windows = config["bundle"]["windows"]

    assert windows["allowDowngrades"] is False
    assert windows["wix"]["upgradeCode"] == "450405c0-85b9-5bc5-a05c-de2bbb1e5805"


def test_application_version_is_consistent_across_build_systems() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    cargo = tomllib.loads(
        (root / "apps" / "desktop" / "src-tauri" / "Cargo.toml").read_text(
            encoding="utf-8"
        )
    )
    package = json.loads(
        (root / "apps" / "desktop" / "package.json").read_text(encoding="utf-8")
    )
    tauri = json.loads(
        (root / "apps" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    project_source = (
        root / "sidecar" / "stt_desktop" / "storage" / "project.py"
    ).read_text(encoding="utf-8")
    versions = {
        pyproject["project"]["version"],
        cargo["package"]["version"],
        package["version"],
        tauri["version"],
    }

    assert versions == {"0.1.2"}
    assert 'APP_VERSION = "0.1.2"' in project_source
