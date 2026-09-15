from copy import deepcopy

import pytest

from stt_desktop.storage import ProjectError, ProjectWorkspace, RevisionConflictError
from stt_desktop.timetable_settings import TimetableSettingsService


@pytest.fixture
def editor(tmp_path):
    with ProjectWorkspace(tmp_path).create_project("测试课表") as project:
        yield TimetableSettingsService(project)


def bundle(name="测试模板"):
    return {
        "template": {
            "name": name,
            "day_count": 7,
            "slot_duration_minutes": 5,
            "template_kind": "normal",
            "display_config": {
                "enabled_weekdays": [1, 2, 3, 4, 5],
                "header_rows": [
                    {"id": "header", "cells": {"1": {"label": "第一学期", "colspan": 3}}}
                ],
                "blank_columns": [{"id": "备注", "cells": {}}],
            },
        },
        "periods": [
            {
                "weekday": d,
                "period_index": i + 1,
                "label": f"第{i + 1}节",
                "start_time_minutes": 480 + i * 50,
                "end_time_minutes": 520 + i * 50,
                "active": True,
                "display_config": {"cell_mode": "scheduled", "align": "center"},
            }
            for d in range(1, 8)
            for i in range(2)
        ],
    }


def saved_bundle(editor, template_id):
    school = editor.read()["schoolData"]
    return {
        "template": next(t for t in school["weekly_timetable_templates"] if t["id"] == template_id),
        "periods": [
            p for p in school["weekly_timetable_periods"] if p["template_id"] == template_id
        ],
    }


def test_roundtrip_layout_and_solver_slot_units(editor):
    data = bundle()
    result = editor.save(data, 0)
    saved = saved_bundle(editor, result["templateId"])
    assert saved["template"]["display_config"] == data["template"]["display_config"]
    assert saved["template"]["slot_duration_minutes"] == 5
    assert saved["template"]["is_default"] is True
    local = editor.project.list_entities("time_slot")
    assert all(
        row["start_slot"] == row["period_index"] and row["length_slots"] == 1 for row in local
    )
    assert all(row["active"] == int(row["weekday"] <= 5) for row in local)
    assert all(p["active"] is True for p in saved["periods"])
    ids = {row["id"] for row in local}
    editor.save(saved, 1)
    assert {row["id"] for row in editor.project.list_entities("time_slot")} == ids
    assert editor.project.integrity_check()["integrity"] == "ok"


def test_invalid_time_and_stale_revision_are_atomic(editor):
    result = editor.save(bundle(), 0)
    before = deepcopy(editor.read())
    data = saved_bundle(editor, result["templateId"])
    data["template"]["name"] = "不能保存"
    data["periods"][1]["start_time_minutes"] = 500
    with pytest.raises(ProjectError, match="重叠"):
        editor.save(data, 1)
    assert editor.read() == before
    with pytest.raises(RevisionConflictError):
        editor.save(bundle(), 0)
    assert editor.read() == before


def test_reuse_follows_source_and_preserves_child_ids(editor):
    source = editor.save(bundle(), 0)["templateId"]
    child_data = bundle("复用模板")
    child_data["template"].update(period_source_template_id=source, periods_locked=True)
    child = editor.save(child_data, 1)["templateId"]
    child_ids = {p["id"] for p in saved_bundle(editor, child)["periods"]}
    source_data = saved_bundle(editor, source)
    source_data["periods"][0]["end_time_minutes"] = 515
    editor.save(source_data, 2)
    child_periods = saved_bundle(editor, child)["periods"]
    assert {p["id"] for p in child_periods} == child_ids
    assert child_periods[0]["end_time_minutes"] == 515
    with pytest.raises(ProjectError, match="复用"):
        editor.delete(source, 3)


def test_referenced_period_cannot_be_deleted(editor):
    template_id = editor.save(bundle(), 0)["templateId"]
    saved = saved_bundle(editor, template_id)
    slot_id = saved["periods"][0]["id"]
    editor.project.save_entity(
        "availability_rule",
        {
            "entity_type": "teacher",
            "entity_id": "test",
            "time_slot_id": slot_id,
            "week_bits": "1",
            "day_bits": "1",
            "required": 1,
        },
        1,
    )
    saved["periods"] = saved["periods"][1:]
    with pytest.raises(ProjectError, match="引用"):
        editor.save(saved, 2)
    with pytest.raises(ProjectError, match="引用"):
        editor.delete(template_id, 2)
    assert editor.project.revision == 2
    assert editor.project.get_entity("time_slot", slot_id)


def test_custom_cell_metadata_retained_but_not_scheduled(editor):
    data = bundle()
    data["periods"][0].update(
        active=False,
        display_config={"cell_mode": "custom", "custom_content": "升旗仪式", "colspan": 2},
    )
    tid = editor.save(data, 0)["templateId"]
    saved = saved_bundle(editor, tid)
    cell = next(p for p in saved["periods"] if p["weekday"] == 1 and p["period_index"] == 1)
    assert cell["display_config"]["custom_content"] == "升旗仪式"
    assert cell["display_config"]["colspan"] == 2
    assert cell["active"] is False


def test_insert_and_reorder_preserve_period_identity(editor):
    tid = editor.save(bundle(), 0)["templateId"]
    data = saved_bundle(editor, tid)
    monday = [p for p in data["periods"] if p["weekday"] == 1]
    for period in monday:
        period["period_index"] += 1
    inserted = {
        **monday[0],
        "id": None,
        "period_index": 1,
        "start_time_minutes": 400,
        "end_time_minutes": 440,
    }
    data["periods"].insert(0, inserted)
    editor.save(data, 1)
    assert editor.project.get_entity("time_slot", monday[0]["id"])["period_index"] == 1


def test_delete_promotes_remaining_normal_template(editor):
    first = editor.save(bundle("第一份"), 0)["templateId"]
    second = editor.save(bundle("第二份"), 1)["templateId"]
    editor.delete(first, 2)
    assert saved_bundle(editor, second)["template"]["is_default"] is True


def test_api_auth_revision_save_backup_and_reload(tmp_path):
    from fastapi.testclient import TestClient
    from stt_desktop.api.app import create_app
    from stt_desktop.service_config import AppServiceConfig

    token = "t" * 64
    workspace = ProjectWorkspace(tmp_path)
    app = create_app(
        workspace=workspace,
        services=AppServiceConfig(1, "test", True, {}),
        session_token=token,
        enforce_loopback=False,
    )
    auth = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as api:
        assert api.get("/v1/timetable/settings").status_code == 401
        project = api.post("/v1/projects", headers=auth, json={"name": "本地测试"}).json()
        saved = api.put(
            "/v1/timetable/templates", headers=auth, json={"expected_revision": 0, "data": bundle()}
        )
        assert saved.status_code == 200, saved.text
        tid = saved.json()["templateId"]
        data = bundle("新名称")
        data["template"]["id"] = tid
        saved = api.put(
            "/v1/timetable/templates", headers=auth, json={"expected_revision": 1, "data": data}
        )
        assert saved.status_code == 200, saved.text
        assert list(workspace.backups_directory.rglob("*.sttbackup"))
        invalid = api.put(
            "/v1/timetable/templates",
            headers=auth,
            json={"expected_revision": 2, "data": {"template": [], "periods": []}},
        )
        assert invalid.status_code == 400
        api.post("/v1/projects/current/close", headers=auth)
        api.post(f"/v1/projects/{project['project']['id']}/open", headers=auth)
        read = api.get("/v1/timetable/settings", headers=auth).json()
        assert read["schoolData"]["weekly_timetable_templates"][0]["name"] == "新名称"
        assert read["revision"] == 2
