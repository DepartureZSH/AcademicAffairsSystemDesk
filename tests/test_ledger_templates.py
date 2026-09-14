"""Ledger template fields reuse the same assignments as the timetable editor."""

import sqlite3
from pathlib import Path

import pytest

from stt_desktop.storage import ProjectError, ProjectWorkspace, RevisionConflictError
from stt_desktop.timetable_settings import TimetableSettingsService


@pytest.fixture
def project(tmp_path):
    with ProjectWorkspace(tmp_path).create_project("模板台账") as repository:
        yield repository


def save(project, kind, **data):
    return project.save_entity(kind, data, project.revision)[0]


@pytest.mark.parametrize("kind", ["teacher", "homeroom", "room_type"])
def test_ledger_template_atomic_create_change_clear_and_reload(project, kind):
    first = save(project, "bell_schedule", name="第一份")
    second = save(project, "bell_schedule", name="第二份")
    start = project.revision
    record = save(project, kind, name="记录", export_template_id=first["id"])
    assert project.revision == start + 1
    assignment = project.list_entities("timetable_template_assignment")[0]
    assert assignment["entity_type"] == kind
    assert assignment["entity_id"] == record["id"]
    assert assignment["bell_schedule_id"] == first["id"]
    # Name-only edits must preserve assignments; ID-only template edits also work.
    save(project, kind, id=record["id"], name="重命名")
    assert project.list_entities("timetable_template_assignment")[0] == assignment
    save(project, kind, id=record["id"], export_template_id=second["id"])
    changed = TimetableSettingsService(project).read()["schoolData"][
        "timetable_template_assignments"
    ]
    assert len(changed) == 1
    assert changed[0]["id"] == assignment["id"]
    assert changed[0]["bell_schedule_id"] == second["id"]
    save(project, kind, id=record["id"], export_template_id=None)
    assert not project.list_entities("timetable_template_assignment")
    assert project.get_entity(kind, record["id"])["name"] == "重命名"
    assert project.integrity_check()["integrity"] == "ok"


def test_invalid_template_rolls_back_record_and_revision(project):
    normal = save(project, "bell_schedule", name="普通模板")
    special = save(
        project,
        "bell_schedule",
        name="总课表",
        display_config={"_web_template": {"template_kind": "special"}},
    )
    teacher = save(project, "teacher", name="教师", export_template_id=normal["id"])
    before = project.revision
    for bad in ("missing", "", 123, special["id"]):
        with pytest.raises(ProjectError, match="模板"):
            save(project, "teacher", id=teacher["id"], name="不能落库", export_template_id=bad)
        assert project.revision == before
        assert project.get_entity("teacher", teacher["id"])["name"] == "教师"
        with pytest.raises(ProjectError, match="模板"):
            save(project, "room", name="不能创建", export_template_id=bad)
        assert not project.list_entities("room")
    with pytest.raises(RevisionConflictError):
        project.save_entity(
            "teacher", {"id": teacher["id"], "export_template_id": None}, before - 1
        )
    assert (
        project.list_entities("timetable_template_assignment")[0]["bell_schedule_id"]
        == normal["id"]
    )


def test_delete_cleans_assignment_and_failed_delete_preserves_it(project):
    template = save(project, "bell_schedule", name="普通模板")
    teacher = save(project, "teacher", name="教师", export_template_id=template["id"])
    project.connection.execute(
        "CREATE TRIGGER prevent_teacher_delete BEFORE DELETE ON teachers "
        "BEGIN SELECT RAISE(ABORT, 'test blocked deletion'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        project.delete_entity("teacher", teacher["id"], project.revision)
    assert len(project.list_entities("timetable_template_assignment")) == 1
    project.connection.execute("DROP TRIGGER prevent_teacher_delete")
    project.delete_entity("teacher", teacher["id"], project.revision)
    assert not project.list_entities("timetable_template_assignment")


def test_ledger_ui_has_template_column_and_defaults():
    source = (
        Path(__file__).parents[1] / "apps/desktop/src/components/SchoolDataView.vue"
    ).read_text(encoding="utf-8")
    assert 'data-label="导出模板"' in source
    assert 'v-model="exportTemplateId"' in source
    assert "data.export_template_id = exportTemplateId.value || null" in source
    assert "assignedTemplateId(activeType.value, item.id)" in source
    assert 'loadTemplateLookup("timetable_template_assignment")' in source


def test_room_cannot_override_type_template(project):
    template = save(project, 'bell_schedule', name='类型模板')
    room_type = save(project, 'room_type', name='普通教室', export_template_id=template['id'])
    room = save(project, 'room', name='一号教室', room_type_id=room_type['id'])
    before = project.revision
    with pytest.raises(ProjectError, match='沿用教室类型'):
        save(project, 'room', id=room['id'], export_template_id=template['id'])
    with pytest.raises(ProjectError, match='沿用教室类型'):
        save(project, 'timetable_template_assignment', entity_type='room', entity_id=room['id'], bell_schedule_id=template['id'])
    assert project.revision == before
    assert project.list_entities('timetable_template_assignment')[0]['entity_id'] == room_type['id']
