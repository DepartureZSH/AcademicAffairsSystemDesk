from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

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


MAX_ARCHIVE_FILES = 20_000
MAX_UNCOMPRESSED_BYTES = 5 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_000
AUTOMATIC_REASONS = {"daily", "pre-import", "pre-migration", "pre-destructive"}


class BackupService:
    def __init__(self, project: ProjectRepository, workspace: ProjectWorkspace) -> None:
        self.project = project
        self.workspace = workspace

    def create_backup(
        self,
        *,
        reason: str,
        retained: bool = False,
        destination_path: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 200:
            raise ProjectError("备份原因必须为 1 到 200 个字符")
        project_id = self.project.project_info()["id"]
        backup_id = uuid7()
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        directory = (self.workspace.backups_directory / project_id).resolve()
        if directory.parent != self.workspace.backups_directory:
            raise ProjectError("备份目录越界")
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{timestamp}-{backup_id}.sttbackup"
        staging = (self.workspace.temp_directory / f"backup-{backup_id}").resolve()
        if staging.parent != self.workspace.temp_directory:
            raise ProjectError("备份临时目录越界")
        staging.mkdir()
        temporary_archive = target.with_name(f".{target.name}.{uuid7()}.tmp")
        try:
            project_stage = staging / "project"
            self._stage_project(project_stage)
            files = self._manifest_files(project_stage)
            archive_manifest = {
                "kind": "backup",
                "formatVersion": FORMAT_VERSION,
                "backupId": backup_id,
                "createdAt": utc_now(),
                "reason": normalized_reason,
                "sourceProjectId": project_id,
                "sourceProjectName": self.project.project_info()["name"],
                "sourceRevision": self.project.revision,
                "appVersion": APP_VERSION,
                "schemaVersion": self.project.schema_version,
                "files": files,
            }
            _atomic_write_json(staging / "backup-manifest.json", archive_manifest)
            with zipfile.ZipFile(
                temporary_archive,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
                strict_timestamps=True,
            ) as archive:
                archive.write(staging / "backup-manifest.json", "backup-manifest.json")
                for item in files:
                    source = project_stage / item["path"]
                    archive.write(source, f"project/{item['path']}")
            self.verify_archive(temporary_archive)
            with temporary_archive.open("r+b") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary_archive, target)
            sha256, size = self._file_digest(target)
            relative = target.relative_to(self.workspace.root).as_posix()
            self.project.connection.execute(
                """
                INSERT INTO backup_records(id, reason, revision, relative_path, sha256, retained, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (backup_id, normalized_reason, self.project.revision, relative, sha256, int(retained), utc_now()),
            )
            destination = None
            if destination_path:
                destination = self._copy_to_destination(target, destination_path, overwrite)
            if normalized_reason in AUTOMATIC_REASONS:
                self._prune_automatic_backups()
            return {
                "id": backup_id,
                "reason": normalized_reason,
                "revision": self.project.revision,
                "relativePath": relative,
                "fileName": target.name,
                "sha256": sha256,
                "sizeBytes": size,
                "retained": retained,
                "destinationPath": destination,
                "verified": True,
            }
        finally:
            temporary_archive.unlink(missing_ok=True)
            self._remove_verified_temp(staging)

    def create_daily_backup_if_needed(self) -> dict[str, Any] | None:
        today = datetime.now().astimezone().date()
        row = self.project.connection.execute(
            "SELECT created_at FROM backup_records WHERE reason = 'daily' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
            if created.astimezone().date() == today:
                return None
        return self.create_backup(reason="daily")

    def list_backups(self) -> list[dict[str, Any]]:
        rows = self.project.connection.execute(
            "SELECT * FROM backup_records ORDER BY created_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            path = (self.workspace.root / item["relative_path"]).resolve()
            item["exists"] = path.is_file() and self.workspace.backups_directory in path.parents
            item["size_bytes"] = path.stat().st_size if item["exists"] else None
            result.append(item)
        return result

    def set_retained(self, backup_id: str, retained: bool) -> dict[str, Any]:
        cursor = self.project.connection.execute(
            "UPDATE backup_records SET retained = ? WHERE id = ?", (int(retained), backup_id)
        )
        if cursor.rowcount != 1:
            raise ProjectError("备份记录不存在")
        return dict(
            self.project.connection.execute(
                "SELECT * FROM backup_records WHERE id = ?", (backup_id,)
            ).fetchone()
        )

    def verify_record(self, backup_id: str) -> dict[str, Any]:
        row = self.project.connection.execute(
            "SELECT * FROM backup_records WHERE id = ?", (backup_id,)
        ).fetchone()
        if not row:
            raise ProjectError("备份记录不存在")
        path = (self.workspace.root / row["relative_path"]).resolve()
        if self.workspace.backups_directory not in path.parents:
            raise ProjectError("备份记录路径越界")
        manifest = self.verify_archive(path)
        sha256, size = self._file_digest(path)
        if sha256 != row["sha256"]:
            raise ProjectError("备份文件 SHA-256 与记录不一致")
        return {"valid": True, "sha256": sha256, "sizeBytes": size, "manifest": manifest}

    def record_path(self, backup_id: str) -> Path:
        row = self.project.connection.execute(
            "SELECT relative_path FROM backup_records WHERE id = ?", (backup_id,)
        ).fetchone()
        if not row:
            raise ProjectError("备份记录不存在")
        path = (self.workspace.root / row["relative_path"]).resolve()
        if self.workspace.backups_directory not in path.parents or path.suffix.lower() != ".sttbackup":
            raise ProjectError("备份记录路径无效")
        return path

    @classmethod
    def restore_backup(
        cls,
        workspace: ProjectWorkspace,
        archive_path: str | Path,
        *,
        restored_name: str | None = None,
    ) -> dict[str, Any]:
        source = Path(archive_path).expanduser().resolve()
        if source.suffix.lower() != ".sttbackup" or not source.is_file():
            raise ProjectError("请选择有效的 .sttbackup 文件")
        manifest = cls.verify_archive(source)
        if int(manifest["schemaVersion"]) > SCHEMA_VERSION:
            raise ProjectError("备份来自更高数据结构版本，请先升级应用")
        operation_id = uuid7()
        staging = (workspace.temp_directory / f"restore-{operation_id}").resolve()
        if staging.parent != workspace.temp_directory:
            raise ProjectError("恢复临时目录越界")
        staging.mkdir()
        try:
            cls._safe_extract(source, staging)
            project_stage = staging / "project"
            database = project_stage / "project.sqlite3"
            project_manifest_path = project_stage / "manifest.json"
            if not database.is_file() or not project_manifest_path.is_file():
                raise ProjectError("备份缺少项目数据库或 manifest")
            connection = sqlite3.connect(database)
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ProjectError("恢复副本 SQLite 完整性检查失败")
                foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
                if foreign_keys:
                    raise ProjectError("恢复副本存在外键错误")
                schema_version = int(
                    connection.execute(
                        "SELECT value FROM app_metadata WHERE key = 'schema_version'"
                    ).fetchone()[0]
                )
                if schema_version > SCHEMA_VERSION:
                    raise ProjectError("恢复副本数据结构版本高于当前应用")
                revision = int(
                    connection.execute(
                        "SELECT value FROM app_metadata WHERE key = 'revision'"
                    ).fetchone()[0]
                )
                new_project_id = uuid7()
                source_name = str(manifest.get("sourceProjectName") or "恢复项目")
                name = (restored_name or f"{source_name}（恢复 {datetime.now().date().isoformat()}）").strip()
                if not name or len(name) > 200:
                    raise ProjectError("恢复后的项目名称必须为 1 到 200 个字符")
                now = utc_now()
                connection.execute(
                    "UPDATE project SET id = ?, name = ?, updated_at = ?",
                    (new_project_id, name, now),
                )
                connection.commit()
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
                    "restored_from_backup_id": manifest["backupId"],
                }
            )
            _atomic_write_json(project_manifest_path, project_manifest)
            target = (workspace.projects_directory / new_project_id).resolve()
            if target.parent != workspace.projects_directory or target.exists():
                raise ProjectError("恢复目标目录无效或已存在")
            os.replace(project_stage, target)
            try:
                restored = workspace.open_project(new_project_id)
                try:
                    check = restored.integrity_check()
                    if check != {"integrity": "ok", "foreign_key_issues": []}:
                        raise ProjectError("恢复项目最终完整性检查失败")
                finally:
                    restored.close()
            except Exception:
                if target.parent == workspace.projects_directory and target.name == new_project_id:
                    shutil.rmtree(target)
                raise
            return {
                "projectId": new_project_id,
                "name": name,
                "revision": revision,
                "sourceBackupId": manifest["backupId"],
            }
        finally:
            cls._remove_verified_temp(staging, workspace.temp_directory)

    def _stage_project(self, destination: Path) -> None:
        destination.mkdir()
        database_target = destination / "project.sqlite3"
        backup_connection = sqlite3.connect(database_target)
        try:
            self.project.connection.backup(backup_connection)
            backup_connection.commit()
            if backup_connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ProjectError("备份副本 SQLite 完整性检查失败")
        finally:
            backup_connection.close()
        shutil.copyfile(self.project.manifest_path, destination / "manifest.json")
        for folder_name in ("attachments", "artifacts"):
            source = self.project.project_directory / folder_name
            target = destination / folder_name
            if source.exists():
                shutil.copytree(source, target, symlinks=False)

    @classmethod
    def verify_archive(cls, archive_path: str | Path) -> dict[str, Any]:
        source = Path(archive_path)
        if not source.is_file():
            raise ProjectError("备份文件不存在")
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ARCHIVE_FILES:
                raise ProjectError("备份文件条目数量无效")
            total = 0
            names: set[str] = set()
            for info in infos:
                normalized = cls._safe_archive_name(info.filename)
                if normalized in names:
                    raise ProjectError("备份包含重复文件名")
                names.add(normalized)
                if cls._zipinfo_is_symlink(info):
                    raise ProjectError("备份不得包含符号链接")
                total += info.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise ProjectError("备份解压后体积超过限制")
                if info.compress_size == 0 and info.file_size > 0:
                    raise ProjectError("备份包含异常压缩条目")
                if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                    raise ProjectError("备份包含异常压缩比条目")
            if "backup-manifest.json" not in names:
                raise ProjectError("备份缺少 backup-manifest.json")
            manifest = json.loads(archive.read("backup-manifest.json").decode("utf-8"))
            cls._validate_manifest(manifest)
            expected_names = {"backup-manifest.json"} | {
                f"project/{item['path']}" for item in manifest["files"]
            }
            if names != expected_names:
                raise ProjectError("备份文件列表与 manifest 不一致")
            for item in manifest["files"]:
                content = archive.read(f"project/{item['path']}")
                if len(content) != int(item["sizeBytes"]):
                    raise ProjectError("备份文件大小与 manifest 不一致")
                if hashlib.sha256(content).hexdigest() != item["sha256"]:
                    raise ProjectError("备份文件哈希与 manifest 不一致")
            return manifest

    @staticmethod
    def _validate_manifest(manifest: dict[str, Any]) -> None:
        required = {
            "kind", "formatVersion", "backupId", "createdAt", "reason",
            "sourceProjectId", "sourceProjectName", "sourceRevision",
            "appVersion", "schemaVersion", "files",
        }
        if set(manifest) != required or manifest.get("kind") != "backup":
            raise ProjectError("备份 manifest 字段无效")
        if not isinstance(manifest["files"], list) or not manifest["files"]:
            raise ProjectError("备份 manifest 文件列表无效")
        for item in manifest["files"]:
            if set(item) != {"path", "sha256", "sizeBytes"}:
                raise ProjectError("备份 manifest 文件条目无效")
            BackupService._safe_archive_name(f"project/{item['path']}")
            if len(str(item["sha256"])) != 64 or int(item["sizeBytes"]) < 0:
                raise ProjectError("备份 manifest 哈希或大小无效")

    @staticmethod
    def _manifest_files(project_stage: Path) -> list[dict[str, Any]]:
        result = []
        for path in sorted(item for item in project_stage.rglob("*") if item.is_file()):
            if path.is_symlink():
                raise ProjectError("项目目录包含不允许归档的符号链接")
            relative = path.relative_to(project_stage).as_posix()
            sha256, size = BackupService._file_digest(path)
            result.append({"path": relative, "sha256": sha256, "sizeBytes": size})
        return result

    def _prune_automatic_backups(self) -> None:
        rows = self.project.connection.execute(
            """
            SELECT * FROM backup_records
            WHERE retained = 0 AND reason IN ('daily', 'pre-import', 'pre-migration', 'pre-destructive')
            ORDER BY created_at DESC
            """
        ).fetchall()
        for row in rows[10:]:
            path = (self.workspace.root / row["relative_path"]).resolve()
            expected_parent = (self.workspace.backups_directory / self.project.project_info()["id"]).resolve()
            if path.parent != expected_parent or path.suffix.lower() != ".sttbackup":
                raise ProjectError("拒绝清理路径不匹配的备份记录")
            path.unlink(missing_ok=True)
            self.project.connection.execute("DELETE FROM backup_records WHERE id = ?", (row["id"],))

    @staticmethod
    def _safe_archive_name(name: str) -> str:
        if "\\" in name or name.startswith(("/", "\\")):
            raise ProjectError("备份包含绝对路径或非 POSIX 路径")
        path = PurePosixPath(name)
        if not name or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ProjectError("备份包含路径穿越条目")
        if path.parts[0].endswith(":"):
            raise ProjectError("备份包含驱动器绝对路径")
        return path.as_posix()

    @staticmethod
    def _zipinfo_is_symlink(info: zipfile.ZipInfo) -> bool:
        mode = (info.external_attr >> 16) & 0xFFFF
        return stat.S_ISLNK(mode)

    @classmethod
    def _safe_extract(cls, source: Path, destination: Path) -> None:
        with zipfile.ZipFile(source, "r") as archive:
            for info in archive.infolist():
                name = cls._safe_archive_name(info.filename)
                if cls._zipinfo_is_symlink(info):
                    raise ProjectError("备份不得包含符号链接")
                target = (destination / Path(*PurePosixPath(name).parts)).resolve()
                if destination not in target.parents:
                    raise ProjectError("备份解压路径越界")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source_handle, target.open("xb") as target_handle:
                    shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)

    @staticmethod
    def _file_digest(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    @staticmethod
    def _copy_to_destination(source: Path, destination_path: str, overwrite: bool) -> str:
        destination = Path(destination_path).expanduser().resolve()
        if destination.suffix.lower() != ".sttbackup":
            raise ProjectError("备份目标扩展名必须是 .sttbackup")
        if not destination.parent.is_dir():
            raise ProjectError("备份目标目录不存在")
        if destination.exists() and not overwrite:
            raise ProjectError("备份目标已存在，必须明确确认覆盖")
        temporary = destination.with_name(f".{destination.name}.{uuid7()}.tmp")
        try:
            shutil.copyfile(source, temporary)
            with temporary.open("r+b") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return str(destination)

    @staticmethod
    def _remove_verified_temp(path: Path, expected_parent: Path | None = None) -> None:
        if not path.exists():
            return
        resolved = path.resolve()
        parent = (expected_parent or resolved.parent).resolve()
        if resolved.parent != parent or not resolved.name.startswith(("backup-", "restore-")):
            raise ProjectError("拒绝清理未验证的临时目录")
        shutil.rmtree(resolved)
