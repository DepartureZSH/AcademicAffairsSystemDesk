from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from stt_desktop.backups import BackupService
from stt_desktop.project_archives import PACKAGE_MANIFEST, ProjectArchiveService
from stt_desktop.storage import ProjectError, ProjectWorkspace


def project_fixture(tmp_path: Path):
    workspace = ProjectWorkspace(tmp_path / "workspace")
    project = workspace.create_project("2026 秋季排课")
    project.save_entity(
        "teacher",
        {"employee_no": "T001", "name": "张老师", "department": "数学组"},
        0,
    )
    attachment = project.project_directory / "attachments" / "导入说明.txt"
    attachment.write_text("只在本地保存", encoding="utf-8")
    BackupService(project, workspace).create_backup(reason="manual", retained=True)
    return workspace, project


def test_project_archive_round_trip_creates_a_new_verified_project(tmp_path: Path) -> None:
    workspace, project = project_fixture(tmp_path)
    destination = tmp_path / "秋季排课.sttproj"
    try:
        exported = ProjectArchiveService(project, workspace).export_project(
            str(destination)
        )
        assert exported["verified"]
        assert exported["destinationPath"] == str(destination.resolve())
        manifest = ProjectArchiveService.verify_archive(destination)
        assert manifest["kind"] == "project-package"
        assert manifest["sourceProjectId"] == project.project_info()["id"]

        imported = ProjectArchiveService.import_project(
            workspace, destination, imported_name="导入副本"
        )
        assert imported["projectId"] != project.project_info()["id"]
        copy = workspace.open_project(imported["projectId"])
        try:
            assert copy.project_info()["name"] == "导入副本"
            assert copy.revision == project.revision
            assert copy.list_entities("teacher")[0]["name"] == "张老师"
            assert (
                copy.project_directory / "attachments" / "导入说明.txt"
            ).read_text(encoding="utf-8") == "只在本地保存"
            assert copy.connection.execute("SELECT COUNT(*) FROM backup_records").fetchone()[0] == 0
            assert copy.integrity_check() == {
                "integrity": "ok",
                "foreign_key_issues": [],
            }
        finally:
            copy.close()
        assert len(workspace.list_projects()) == 2
    finally:
        project.close()


def test_save_as_creates_verified_editable_copy_and_removes_temporary_package(
    tmp_path: Path,
) -> None:
    workspace, project = project_fixture(tmp_path)
    source_id = project.project_info()["id"]
    try:
        cloned = ProjectArchiveService(project, workspace).clone_project("2026 秋季排课副本")
        assert cloned["projectId"] != source_id
        assert cloned["sourceProjectId"] == source_id
        assert cloned["verifiedPackageId"] == cloned["sourcePackageId"]
        assert not list(workspace.temp_directory.glob("project-save-as-*.sttproj"))
        copy = workspace.open_project(cloned["projectId"])
        try:
            assert copy.project_info()["name"] == "2026 秋季排课副本"
            assert copy.list_entities("teacher")[0]["name"] == "张老师"
            copy.save_entity(
                "teacher",
                {"employee_no": "T002", "name": "李老师"},
                copy.revision,
            )
            assert len(copy.list_entities("teacher")) == 2
            assert len(project.list_entities("teacher")) == 1
        finally:
            copy.close()
    finally:
        project.close()


def test_project_archive_refuses_overwrite_and_invalid_extension(tmp_path: Path) -> None:
    workspace, project = project_fixture(tmp_path)
    destination = tmp_path / "已有项目.sttproj"
    destination.write_bytes(b"existing")
    try:
        service = ProjectArchiveService(project, workspace)
        with pytest.raises(ProjectError, match="明确确认覆盖"):
            service.export_project(str(destination))
        exported = service.export_project(str(destination), overwrite=True)
        assert exported["verified"]
        with pytest.raises(ProjectError, match="扩展名"):
            service.export_project(str(tmp_path / "project.zip"))
        with pytest.raises(ProjectError, match="有效的 .sttproj"):
            ProjectArchiveService.import_project(workspace, tmp_path / "missing.sttproj")
    finally:
        project.close()


def test_project_archive_rejects_traversal_tampering_and_manifest_mismatch(
    tmp_path: Path,
) -> None:
    traversal = tmp_path / "traversal.sttproj"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../outside.txt", "bad")
    with pytest.raises(ProjectError, match="路径穿越"):
        ProjectArchiveService.verify_archive(traversal)

    workspace, project = project_fixture(tmp_path / "source")
    valid = tmp_path / "valid.sttproj"
    try:
        ProjectArchiveService(project, workspace).export_project(str(valid))
        tampered = tmp_path / "tampered.sttproj"
        with zipfile.ZipFile(valid, "r") as original, zipfile.ZipFile(
            tampered, "w"
        ) as changed:
            for info in original.infolist():
                content = original.read(info.filename)
                if info.filename == "project/manifest.json":
                    content += b" "
                changed.writestr(info, content)
        with pytest.raises(ProjectError, match="大小|哈希"):
            ProjectArchiveService.verify_archive(tampered)

        mismatch = tmp_path / "mismatch.sttproj"
        with zipfile.ZipFile(valid, "r") as original:
            contents = {
                info.filename: original.read(info.filename)
                for info in original.infolist()
            }
        package = json.loads(contents[PACKAGE_MANIFEST].decode("utf-8"))
        package["sourceRevision"] += 1
        contents[PACKAGE_MANIFEST] = json.dumps(package).encode("utf-8")
        with zipfile.ZipFile(mismatch, "w", compression=zipfile.ZIP_DEFLATED) as changed:
            for name, content in contents.items():
                changed.writestr(name, content)
        with pytest.raises(ProjectError, match="Revision|manifest"):
            ProjectArchiveService.import_project(workspace, mismatch)
    finally:
        project.close()
