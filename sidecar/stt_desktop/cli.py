from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from stt_desktop.importers import LegacySupabaseImporter
from stt_desktop.service_config import ConfigError, load_service_config
from stt_desktop.storage import ProjectWorkspace


def _legacy_importer(config_path: Path) -> LegacySupabaseImporter:
    config = load_service_config(config_path)
    service = config.service("legacy_data")
    if service.mode != "real":
        raise ConfigError("legacy_data 不是 real 模式，不能执行旧版数据迁移")
    variable_name = service.env.get("database_url")
    if not variable_name:
        raise ConfigError("legacy_data 未配置 database_url 环境变量名称")
    database_url = os.environ.get(variable_name)
    if not database_url:
        raise ConfigError(f"缺少环境变量: {variable_name}")
    return LegacySupabaseImporter(database_url)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stt-desktop")
    parser.add_argument(
        "--services-config", type=Path, default=Path("config/services.yaml")
    )
    commands = parser.add_subparsers(dest="command", required=True)
    legacy = commands.add_parser("legacy", help="迁移旧版 Supabase 项目")
    legacy_commands = legacy.add_subparsers(dest="legacy_command", required=True)
    discover = legacy_commands.add_parser("discover", help="列出可迁移项目")
    discover.add_argument("--redact-names", action="store_true")
    migrate = legacy_commands.add_parser("import", help="导入指定项目到本地工作区")
    migrate.add_argument("--project-id", required=True)
    migrate.add_argument("--workspace", type=Path, required=True)
    migrate.add_argument("--name")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    importer = _legacy_importer(args.services_config)
    if args.legacy_command == "discover":
        payload = []
        for project in importer.discover_projects():
            payload.append(
                {
                    "project_id": project.project_id,
                    "name": "***" if args.redact_names else project.name,
                    "task_count": project.task_count,
                    "lesson_count": project.lesson_count,
                    "candidate_count": project.candidate_count,
                }
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.legacy_command == "import":
        workspace = ProjectWorkspace(args.workspace)
        repository, result = importer.import_project(
            args.project_id, workspace, target_name=args.name
        )
        try:
            payload = {
                "project_id": result.project_id,
                "revision": result.revision,
                "counts": result.counts,
                "warnings": result.warnings,
                "integrity": repository.integrity_check(),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        finally:
            repository.close()
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
