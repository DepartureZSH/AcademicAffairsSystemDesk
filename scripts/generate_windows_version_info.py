from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_CONFIG = ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"


def numeric_version(version: str) -> tuple[int, int, int, int]:
    parts = version.split(".")
    if not 1 <= len(parts) <= 4 or any(not part.isdigit() for part in parts):
        raise ValueError(f"Windows 版本必须由 1 到 4 个数字段组成: {version}")
    numbers = [int(part) for part in parts]
    if any(number > 65535 for number in numbers):
        raise ValueError(f"Windows 版本字段不能超过 65535: {version}")
    return tuple((numbers + [0] * 4)[:4])  # type: ignore[return-value]


def render_version_info(config: dict[str, object]) -> str:
    version = str(config["version"])
    product_name = str(config["productName"])
    bundle = config["bundle"]
    if not isinstance(bundle, dict):
        raise ValueError("Tauri bundle 配置无效")
    company_name = str(bundle["publisher"])
    copyright_notice = str(bundle["copyright"])
    numeric = numeric_version(version)
    values = [
        ("CompanyName", company_name),
        ("FileDescription", f"{product_name} 本地排课 Sidecar"),
        ("FileVersion", version),
        ("InternalName", "stt-sidecar"),
        ("LegalCopyright", copyright_notice),
        ("OriginalFilename", "stt-sidecar.exe"),
        ("ProductName", product_name),
        ("ProductVersion", version),
    ]
    strings = ",\n".join(
        f"          StringStruct({key!r}, {value!r})" for key, value in values
    )
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric!r},
    prodvers={numeric!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404B0',
        [
{strings}
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PyInstaller Windows version metadata")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_version_info(config), encoding="utf-8", newline="\n")
    print(f"Windows version info: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
