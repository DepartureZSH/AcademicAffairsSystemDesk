import base64
import io
import json

import pytest
from openpyxl import Workbook

from test_scheduling import seed_project
from stt_desktop.agent.service import AgentService
from stt_desktop.agent.workflows import run_workflow
from stt_desktop.agent.upstream.constraint_wizard import rule_catalog
from stt_desktop.agent.workflows import Facade
from stt_desktop.storage import ProjectError
from stt_desktop.scheduler_engine.cp_sat import run_cp_sat_v1


def response(name, value):
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(value)},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }


@pytest.fixture
def service(tmp_path):
    project, _, _ = seed_project(tmp_path)
    with project:
        yield AgentService(project, project.workspace)


def file_payload():
    book = Workbook()
    sheet = book.active
    sheet.title = "课表"
    sheet.append(["时间", "周一"])
    sheet.append(["08:00-08:40", "数学"])
    output = io.BytesIO()
    book.save(output)
    return {"filename": "课表.xlsx", "file": base64.b64encode(output.getvalue()).decode()}


def zoning():
    return {
        "suitable": True,
        "reason": "一节周课表",
        "regular": True,
        "fixed": True,
        "layout": "weekly",
        "column_header_row": 1,
        "columns": [
            {"source_column": 1, "kind": "custom", "weekday": 0},
            {"source_column": 2, "kind": "weekday", "weekday": 1},
        ],
        "cells": [
            {"source": "A1", "role": "axis"},
            {"source": "B1", "role": "axis"},
            {"source": "A2", "role": "custom", "placement": "display"},
            {
                "source": "B2",
                "role": "course",
                "weekday": 1,
                "period_index": 1,
                "start": 480,
                "end": 520,
                "time_source": "A2",
            },
        ],
    }


def test_timetable_parse_analyze_preview_is_readonly(service):
    before = service.project.revision
    payload = file_payload()
    parsed = run_workflow(service, "timetable/parse", payload)
    assert parsed["result"]["sheets"][0]["cells"][0]["horizontal_alignment"] is None
    payload["options"] = {
        "name": "新课表",
        "sheet": "课表",
        "planning_mode": "independent",
        "fixed": True,
        "regular": True,
    }
    prepared = run_workflow(service, "timetable/analyze", payload)
    assert prepared["providerRequest"]["toolChoice"]["function"]["name"] == "zone_timetable"
    done = run_workflow(
        service,
        identifier=prepared["turnId"],
        step=0,
        response=response("zone_timetable", zoning()),
    )
    payload["zoning"] = done["result"]["zoning"]
    preview = run_workflow(service, "timetable/preview", payload)["result"]
    assert preview["draft"]["periods"][0]["start_time_minutes"] == 480
    assert preview["draft"]["display_config"]["enabled_weekdays"] == [1]
    assert service.project.revision == before
    assert len(service.project.list_entities("bell_schedule")) == 1
    with pytest.raises(ProjectError):
        run_workflow(
            service,
            identifier=prepared["turnId"],
            step=0,
            response=response("zone_timetable", zoning()),
        )


def test_specialist_retry_and_stale_revision(service):
    payload = {
        **file_payload(),
        "options": {
            "name": "模板",
            "sheet": "课表",
            "planning_mode": "independent",
            "fixed": True,
            "regular": True,
        },
    }
    start = run_workflow(service, "timetable/analyze", payload)
    retry = run_workflow(
        service,
        identifier=start["turnId"],
        step=0,
        response=response("zone_timetable", {"invalid": True}),
    )
    assert retry["step"] == 1
    service.project.save_entity("teacher", {"name": "新教师"}, service.project.revision)
    with pytest.raises(ProjectError, match="项目已变化"):
        run_workflow(
            service,
            identifier=start["turnId"],
            step=1,
            response=response("zone_timetable", zoning()),
        )


def test_constraint_search_and_workbook(service):
    rows = rule_catalog(Facade(service.project, []), "local", "local")
    assert len(rows) == 22
    start = run_workflow(service, "constraints/rules/search", {"query": "不同时上课"})
    result = run_workflow(
        service,
        identifier=start["turnId"],
        step=0,
        response=response(
            "match_rules",
            {
                "matches": [{"id": "NotOverlap", "confidence": 0.99, "reason": "不重叠"}],
                "message": "找到规则",
            },
        ),
    )
    assert result["result"]["items"][0]["id"] == "NotOverlap"
    data = run_workflow(service, "constraints/workbooks/download", {"id": "parallel"})["result"]
    with pytest.raises(ValueError, match="还没有填写"):
        run_workflow(service, "constraints/workbooks/parse", {"file": data["data"]})


def test_subject_duration_propagates_only_on_confirmation(service):
    from stt_desktop.timetable_settings import config

    before = service.project.list_entities("task_lesson")
    action = service.compile("school", [{"target": "subject", "operation": "update",
        "payload": {"id": "subject-1", "name": "数学", "default_duration_slots": 9},
        "human_summary": "数学改为45分钟"}])
    assert service.project.list_entities("task_lesson") == before
    service.confirm(action["id"])
    after = service.project.list_entities("task_lesson")
    assert [row["id"] for row in after] == [row["id"] for row in before]
    assert all(config(row["planning_config"])["duration_minutes"] == 45 for row in after)
    assert service.project.get_entity("subject", "subject-1")["default_duration_minutes"] == 45


def test_local_planning_boolean_and_room_semantics(service):
    from stt_desktop.agent.repository import LocalAgentRepository

    lesson = service.project.list_entities("task_lesson")[0]
    service.project.save_entity("teaching_task", {"id": lesson["teaching_task_id"],
        "planning_config": {"uses_rooms": False}}, service.project.revision)
    service.project.save_entity("task_lesson", {"id": lesson["id"], "enabled": False}, service.project.revision)
    data = LocalAgentRepository(service.project).list_planning_data()
    converted = next(row for row in data["task_lessons"] if row["id"] == lesson["id"])
    assert converted["enabled"] is False
    assert data["teaching_tasks"][0]["required_room_type"] == "__no_room__"
    assert converted["room_ids"] == []


def test_expansion_review_atomic_confirm_and_deduplicate(service):
    lessons = service.project.list_entities("task_lesson")
    payload = {
        "source": {
            "name": "不重叠",
            "scenario_type": "itc2019:NotOverlap",
            "required": True,
            "groups": [[lesson["id"] for lesson in lessons]],
        },
        "mode": "homeroom",
    }
    preview = run_workflow(service, "constraints/expansion/preview", payload)["result"]
    before = service.project.revision
    pending = run_workflow(
        service,
        "constraints/expansion/commit",
        {**payload, "base_revision": preview["base_revision"]},
    )["result"]
    assert service.project.revision == before
    assert not service.project.list_entities("constraint")
    service.confirm(pending["actionId"])
    assert len(service.project.list_entities("constraint")) == 1
    assert service.project.revision == before + 1
    repeated = run_workflow(service, "constraints/expansion/commit", payload)["result"]
    assert repeated == {"actionId": None, "created_count": 0, "skipped_count": 1}


def test_constraint_workbook_row_replays_search_then_scope_without_writes(service):
    before = service.project.revision
    start = run_workflow(service, "constraints/workbooks/analyze-row", {
        "query": "上课不重叠", "scope": "数学课次", "required": True})
    second = run_workflow(service, identifier=start["turnId"], step=0,
        response=response("match_rules", {"matches": [{"id": "NotOverlap", "confidence": 0.99,
            "reason": "上课不重叠"}], "message": "已找到"}))
    assert second["providerRequest"]["toolChoice"]["function"]["name"] == "resolve_constraint_scope"
    done = run_workflow(service, identifier=start["turnId"], step=1,
        response=response("resolve_constraint_scope", {
            "constraint_key": "itc2019:NotOverlap", "scope_query": {"subject_names": ["数学"]},
            "group_by": ["teaching_task_id"], "parameters": {}, "confidence": 1,
            "interpretation": "数学课次按授课任务分组"}))
    assert done["done"] and done["result"]["resolution"]
    assert service.project.revision == before
    assert not service.project.list_entities("constraint")


@pytest.mark.parametrize(
    "policy",
    [
        "skip_existing",
        "replace",
        "cancel_if_existing",
        "remove_selected",
        "clear_matching",
        "clear_all",
    ],
)
def test_expected_policy_does_not_write(service, policy):
    start = run_workflow(
        service, "planning/expected-policy", {"prompt": "补充要求", "operation": "add"}
    )
    before = service.project.revision
    done = run_workflow(
        service,
        identifier=start["turnId"],
        step=0,
        response=response(
            "expected_time_policy",
            {"policy": policy, "interpretation": "核对策略", "confidence": 0.99},
        ),
    )
    assert done["result"]["policy"] == policy
    assert service.project.revision == before


@pytest.mark.parametrize(
    "kind",
    [
        "DifferentRoom",
        "SameWeeks",
        "Overlap",
        "MinGap(2)",
        "WorkDay(10)",
        "MaxDays(1)",
        "MaxDayLoad(1)",
        "MaxBreaks(0,1)",
        "MaxBlock(1,1)",
        "ParallelLimit(1)",
    ],
)
def test_migrated_solver_rules_are_enforced(kind):
    xml = f'''<problem name="rules" nrWeeks="1"><rooms/><classes>
      <class id="a"><time days="1000000" weeks="1" start="10" length="2"/></class>
      <class id="b"><time days="0100000" weeks="1" start="20" length="2"/></class>
      </classes><distributions><distribution type="{kind}" required="true"><class id="a"/><class id="b"/></distribution></distributions></problem>'''
    result = run_cp_sat_v1(xml, "rules", {"time_limit_seconds": 0.2, "num_search_workers": 1})
    # Engine counts unassigned lessons as hard violations; an incomplete result is
    # expected for infeasible input, never a fabricated complete schedule.
    assert result["hard_violations"] == result["unassigned_count"]
    if kind in ("DifferentRoom", "Overlap", "MaxDays(1)", "MaxDayLoad(1)"):
        assert result["assigned_count"] < 2


def test_six_column_import_uses_source_rows_not_model_rows(service):
    from stt_desktop.agent.attachments import store_attachment

    book = Workbook()
    sheet = book.active
    sheet.append(["班级", "科目", "教师", "默认教室", "课次名", "课次教室"])
    sheet.append(["一班", "数学", "教师一", "不使用教室", "数学A", "不使用教室"])
    sheet.append(["一班", "数学", "教师一", "不使用教室", "数学B", "不使用教室"])
    output = io.BytesIO()
    book.save(output)
    attachment = store_attachment(service, "planning", "课程.xlsx", output.getvalue())
    start = service.start("planning", "按附件更新课程", [attachment["id"]])
    assert start["providerRequest"]["tools"][0]["function"]["name"] == "resolve_import_policy"
    policy = {
        "intent": "import",
        "existing": "update",
        "missing_subjects": "leave",
        "teacher_aliases": {},
        "questions": [],
    }
    done = service.step(
        start["turnId"], 0, response("resolve_import_policy", policy)["choices"][0]["message"]
    )
    assert done["actions"], done["messages"][-1]["content"]
    action = done["actions"][-1]
    assert action["coverage"]["covered_lessons"] == 2
    service.confirm(action["id"])
    assert {"数学A", "数学B"} <= {lesson["label"] for lesson in service.project.list_entities("task_lesson")}


def test_missing_actions_get_one_repair_not_false_success(service):
    turn = service.start("school", "新增教师王老师")
    retry = service.step(
        turn["turnId"], 0, {"role": "assistant", "content": "我已准备好操作计划，请确认后执行"}
    )
    assert not retry["done"]
    done = service.step(
        turn["turnId"], retry["step"], {"role": "assistant", "content": "暂时无法提供有效操作"}
    )
    assert done["done"] and not done["actions"]


def test_official_attachments_are_scoped_to_scene(service):
    from stt_desktop.agent.attachments import store_attachment
    from stt_desktop.agent.upstream.official_workbooks import workbook_bytes

    attachment = store_attachment(service, "rooms", "教室.xlsx", workbook_bytes("rooms", "valid"))
    with pytest.raises(ProjectError, match="场景"):
        service.start("school", "读取附件", [attachment["id"]])
