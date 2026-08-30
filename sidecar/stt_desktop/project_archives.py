from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from stt_desktop.backups import BackupService
from stt_desktop.storage.project import (
    APP_VERSION,
    FORMAT_VERSION,
    ProjectError,
    ProjectRepository,
    ProjectWorkspace,
    _atomic_write_json,
    utc_now,
    uuid7,
)
from stt_desktop.storage.schema import SCHEMA_VERSION


PACKAGE_MANIFEST = "project-package.json"


class ProjectArchiveService:
    """Create and import portable, integrity-checked .sttproj packages."""

    def __init__(self, project: ProjectRepository, workspace: ProjectWorkspace) -> None:
        self.project = project
        self.workspace = workspace

    def export_project(
        self, destination_path: str, *, overwrite: bool = False
    ) -> dict[str, Any]:
        destination = Path(destination_path).expanduser().resolve()
        if destination.suffix.lower() != ".sttproj":
            raise ProjectError("项目包扩展名必须是 .sttproj")
        if not destination.parent.is_dir():
            raise ProjectError("项目包目标目录不存在")
        if destination.exists() and not overwrite:
            raise ProjectError("项目包已存在，必须明确确认覆盖")

        package_id = uuid7()
        staging = (self.workspace.temp_directory / f"project-export-{package_id}").resolve()
        if staging.parent != self.workspace.temp_directory:
            raise ProjectError("项目导出临时目录越界")
        staging.mkdir()
        temporary = destination.with_name(f".{destination.name}.{package_id}.tmp")
        try:
            project_stage = staging / "project"
            BackupService(self.project, self.workspace)._stage_project(project_stage)
            files = BackupService._manifest_files(project_stage)
            info = self.project.project_info()
            manifest = {
                "kind": "project-package",
                "formatVersion": FORMAT_VERSION,
                "packageId": package_id,
                "createdAt": utc_now(),
                "sourceProjectId": info["id"],
                "sourceProjectName": info["name"],
                "sourceRevision": self.project.revision,
                "appVersion": APP_VERSION,
                "schemaVersion": SCHEMA_VERSION,
                "files": files,
            }
            _atomic_write_json(staging / PACKAGE_MANIFEST, manifest)
            with zipfile.ZipFile(
                temporary,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
                strict_timestamps=True,
            ) as archive:
                archive.write(staging / PACKAGE_MANIFEST, PACKAGE_MANIFEST)
                for item in files:
                    archive.write(
                        project_stage / item["path"], f"project/{item['path']}"
                    )
            verified = self.verify_archive(temporary)
            with temporary.open("r+b") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            sha256, size = BackupService._file_digest(destination)
            return {
                "packageId": package_id,
                "destinationPath": str(destination),
                "fileName": destination.name,
                "sourceProjectId": info["id"],
                "sourceRevision": self.project.revision,
                "sha256": sha256,
                "sizeBytes": size,
                "verified": verified["packageId"] == package_id,
            }
        finally:
            temporary.unlink(missing_ok=True)
            self._remove_staging(
                staging, self.workspace.temp_directory, "project-export-"
            )

    def clone_project(self, new_name: str) -> dict[str, Any]:
        """Create a verified editable copy inside the same workspace."""
        name = new_name.strip()
        if not name or len(name) > 200:
            raise ProjectError("另存后的项目名称必须为 1 到 200 个字符")
        operation_id = uuid7()
        archive = (
            self.workspace.temp_directory / f"project-save-as-{operation_id}.sttproj"
        ).resolve()
        if archive.parent != self.workspace.temp_directory:
            raise ProjectError("项目另存临时路径越界")
        try:
            package = self.export_project(str(archive))
            imported = self.import_project(
                self.workspace,
                archive,
                imported_name=name,
            )
            return {
                **imported,
                "verifiedPackageId": package["packageId"],
                "sourceRevision": package["sourceRevision"],
            }
        finally:
            if archive.parent == self.workspace.temp_directory:
                archive.unlink(missing_ok=True)

    @classmethod
    def import_project(
        cls,
        workspace: ProjectWorkspace,
        archive_path: str | Path,
        *,
        imported_name: str | None = None,
    ) -> dict[str, Any]:
        source = Path(archive_path).expanduser().resolve()
        if source.suffix.lower() != ".sttproj" or not source.is_file():
            raise ProjectError("请选择有效的 .sttproj 项目包")
        manifest = cls.verify_archive(source)
        if int(manifest["formatVersion"]) > FORMAT_VERSION:
            raise ProjectError("项目包格式来自更高版本，请先升级应用")
        if int(manifest["schemaVersion"]) > SCHEMA_VERSION:
            raise ProjectError("项目包来自更高数据结构版本，请先升级应用")

        operation_id = uuid7()
        staging = (workspace.temp_directory / f"project-import-{operation_id}").resolve()
        if staging.parent != workspace.temp_directory:
            raise ProjectError("项目导入临时目录越界")
        staging.mkdir()
        target: Path | None = None
        try:
            BackupService._safe_extract(source, staging)
            project_stage = staging / "project"
            database = project_stage / "project.sqlite3"
            project_manifest_path = project_stage / "manifest.json"
            if not database.is_file() or not project_manifest_path.is_file():
                raise ProjectError("项目包缺少项目数据库或 manifest")
            try:
                original_project_manifest = json.loads(
                    project_manifest_path.read_text(encoding="utf-8")
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProjectError("项目 manifest 无法解析") from exc
            try:
                manifests_match = (
                    original_project_manifest.get("kind") == "project"
                    and original_project_manifest.get("project_id")
                    == manifest["sourceProjectId"]
                    and int(original_project_manifest.get("revision", -1))
                    == int(manifest["sourceRevision"])
                    and int(original_project_manifest.get("schema_version", -1))
                    == int(manifest["schemaVersion"])
                )
            except (TypeError, ValueError) as exc:
                raise ProjectError("项目 manifest 版本字段无效") from exc
            if not manifests_match:
                raise ProjectError("项目包外层 manifest 与项目 manifest 不一致")

            connection = sqlite3.connect(database)
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ProjectError("导入副本 SQLite 完整性检查失败")
                if connection.execute("PRAGMA foreign_key_check").fetchall():
                    raise ProjectError("导入副本存在外键错误")
                metadata = dict(connection.execute("SELECT key, value FROM app_metadata"))
                schema_version = int(metadata["schema_version"])
                revision = int(metadata["revision"])
                if schema_version > SCHEMA_VERSION:
                    raise ProjectError("导入副本数据结构版本高于当前应用")
                if schema_version != int(manifest["schemaVersion"]):
                    raise ProjectError("项目包 manifest 与数据库结构版本不一致")
                database_project = connection.execute(
                    "SELECT id FROM project"
                ).fetchall()
                if (
                    len(database_project) != 1
                    or database_project[0][0] != manifest["sourceProjectId"]
                    or revision != int(manifest["sourceRevision"])
                ):
                    raise ProjectError("项目包 manifest 与数据库项目标识或 Revision 不一致")

                new_project_id = uuid7()
                source_name = str(manifest.get("sourceProjectName") or "导入项目")
                name = (imported_name or source_name).strip()
                if not name or len(name) > 200:
                    raise ProjectError("导入后的项目名称必须为 1 到 200 个字符")
                now = utc_now()
                connection.execute(
                    "UPDATE project SET id = ?, name = ?, updated_at = ?",
                    (new_project_id, name, now),
                )
                # Workspace-level backup files are intentionally not part of a
                # portable project package, so their source paths must not survive.
                connection.execute("DELETE FROM backup_records")
                connection.commit()
            except (KeyError, TypeError, ValueError) as exc:
                raise ProjectError("项目包数据库元数据无效") from exc
            finally:
                connection.close()

            project_manifest = json.loads(project_manifest_path.read_text(encoding="utf-8"))
            project_manifest.update(
                {
                    "kind": "project",
                    "project_id": new_project_id,
                    "name": name,
                    "updated_at": now,
                    "app_version": APP_VERSION,
                    "schema_version": schema_version,
                    "revision": revision,
                    "imported_from_package_id": manifest["packageId"],
                }
            )
            _atomic_write_json(project_manifest_path, project_manifest)
            target = (workspace.projects_directory / new_project_id).resolve()
            if target.parent != workspace.projects_directory or target.exists():
                raise ProjectError("项目导入目标目录无效或已存在")
            os.replace(project_stage, target)

            imported: ProjectRepository | None = None
            try:
                imported = workspace.open_project(new_project_id)
                if imported.integrity_check() != {
                    "integrity": "ok",
                    "foreign_key_issues": [],
                }:
                    raise ProjectError("导入项目最终完整性检查失败")
            except Exception:
                if imported is not None:
                    imported.close()
                if target.parent == workspace.projects_directory:
                    shutil.rmtree(target)
                raise
            else:
                imported.close()
            return {
                "projectId": new_project_id,
                "name": name,
                "revision": revision,
                "sourcePackageId": manifest["packageId"],
                "sourceProjectId": manifest["sourceProjectId"],
            }
        finally:
            cls._remove_staging(staging, workspace.temp_directory, "project-import-")

    @classmethod
    def verify_archive(cls, archive_path: str | Path) -> dict[str, Any]:
        source = Path(archive_path)
        if not source.is_file():
            raise ProjectError("项目包不存在")
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            if not infos or len(infos) > 20_000:
                raise ProjectError("项目包文件条目数量无效")
            names: set[str] = set()
            total = 0
            for info in infos:
                name = BackupService._safe_archive_name(info.filename)
                if name in names:
                    raise ProjectError("项目包包含重复文件名")
                names.add(name)
                if BackupService._zipinfo_is_symlink(info):
                    raise ProjectError("项目包不得包含符号链接")
                total += info.file_size
                if total > 5 * 1024 * 1024 * 1024:
                    raise ProjectError("项目包解压后体积超过限制")
                if info.compress_size == 0 and info.file_size > 0:
                    raise ProjectError("项目包包含异常压缩条目")
                if info.compress_size and info.file_size / info.compress_size > 1_000:
                    raise ProjectError("项目包包含异常压缩比条目")
            if PACKAGE_MANIFEST not in names:
                raise ProjectError(f"项目包缺少 {PACKAGE_MANIFEST}")
            try:
                manifest = json.loads(archive.read(PACKAGE_MANIFEST).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProjectError("项目包 manifest 无法解析") from exc
            cls._validate_manifest(manifest)
            expected = {PACKAGE_MANIFEST} | {
                f"project/{item['path']}" for item in manifest["files"]
            }
            if names != expected:
                raise ProjectError("项目包文件列表与 manifest 不一致")
            for item in manifest["files"]:
                digest = hashlib.sha256()
                size = 0
                with archive.open(f"project/{item['path']}", "r") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                        size += len(chunk)
                if size != int(item["sizeBytes"]):
                    raise ProjectError("项目包文件大小与 manifest 不一致")
                if digest.hexdigest() != item["sha256"]:
                    raise ProjectError("项目包文件哈希与 manifest 不一致")
            return manifest

    @staticmethod
    def _validate_manifest(manifest: dict[str, Any]) -> None:
        required = {
            "kind",
            "formatVersion",
            "packageId",
            "createdAt",
            "sourceProjectId",
            "sourceProjectName",
            "sourceRevision",
            "appVersion",
            "schemaVersion",
            "files",
        }
        if set(manifest) != required or manifest.get("kind") != "project-package":
            raise ProjectError("项目包 manifest 字段无效")
        if not isinstance(manifest["files"], list) or not manifest["files"]:
            raise ProjectError("项目包 manifest 文件列表无效")
        try:
            if (
                int(manifest["formatVersion"]) < 1
                or int(manifest["sourceRevision"]) < 0
                or int(manifest["schemaVersion"]) < 1
            ):
                raise ProjectError("项目包版本信息无效")
            for item in manifest["files"]:
                if set(item) != {"path", "sha256", "sizeBytes"}:
                    raise ProjectError("项目包 manifest 文件条目无效")
                BackupService._safe_archive_name(f"project/{item['path']}")
                if len(str(item["sha256"])) != 64 or int(item["sizeBytes"]) < 0:
                    raise ProjectError("项目包 manifest 哈希或大小无效")
        except (TypeError, ValueError) as exc:
            raise ProjectError("项目包 manifest 版本或文件大小无效") from exc

    @staticmethod
    def _remove_staging(path: Path, expected_parent: Path, prefix: str) -> None:
        if not path.exists():
            return
        resolved = path.resolve()
        if resolved.parent != expected_parent.resolve() or not resolved.name.startswith(prefix):
            raise ProjectError("拒绝清理未验证的项目包临时目录")
        shutil.rmtree(resolved)
