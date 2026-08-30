# Third-Party Notices

This project redistributes open-source components through the Tauri desktop application and the frozen Python sidecar. Each component remains subject to its own license and copyright notices.

The authoritative inventory for a build is generated from the checked-in Cargo, npm, and Python environments:

```powershell
uv run python scripts\generate_dependency_inventory.py
```

The command writes `build/compliance/dependency-inventory.json`, fails if a distributable dependency does not declare a license, and records package name, version, ecosystem, license expression, and source metadata. Release CI must preserve this inventory with the build evidence. It is intentionally generated rather than copied into this file so dependency upgrades cannot leave a stale manual list.

Major runtime components include Tauri (Apache-2.0/MIT), Vue (MIT), Python, FastAPI (MIT), OR-Tools (Apache-2.0), PyInstaller (GPL-2.0-or-later with a special exception permitting distribution of generated executables), openpyxl (MIT), and ReportLab (BSD). This summary is not a substitute for the generated complete inventory or the license texts shipped by those projects.

No proprietary fonts are bundled. PDF export selects an available system CJK font at runtime and fails clearly when none is available. Application icons are project assets and are additionally subject to [TRADEMARKS.md](TRADEMARKS.md).
