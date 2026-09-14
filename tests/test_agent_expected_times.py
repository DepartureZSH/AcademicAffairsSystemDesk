import json
import pytest
from test_scheduling import seed_project
from stt_desktop.agent.expected_times import read_expected, apply_expected
from stt_desktop.storage import ProjectError


def setup_project(tmp_path):
    project, task, lessons = seed_project(tmp_path, slot_count=3)
    plan, _ = project.save_entity(
        "course_plan",
        {
            "term_id": task["term_id"],
            "homeroom_id": task["homeroom_id"],
            "subject_id": task["subject_id"],
            "weekly_slots": 2,
        },
        project.revision,
    )
    project.save_entity(
        "teaching_task", {"id": task["id"], "course_plan_id": plan["id"]}, project.revision
    )
    return project, lessons


def configuration(slot, penalty=10):
    return {
        "schema_version": 2,
        "default_policy": "restricted",
        "rules": [
            {
                "template_id": slot["bell_schedule_id"],
                "period_keys": [slot["period_index"] + 1],
                "week_bits": "1" * 20,
                "day_bits": "".join("1" if day == slot["weekday"] else "0" for day in range(1, 8)),
                "effect": "preferred",
                "penalty": penalty,
                "required": True,
            }
        ],
    }


def test_apply_and_clear_preserve_ids_and_audit(tmp_path):
    project, lessons = setup_project(tmp_path)
    with project:
        slot = project.list_entities("time_slot")[0]
        before = project.revision
        items = [
            {"lesson_id": lesson["id"], "revision": before, "configuration": configuration(slot)}
            for lesson in lessons
        ]
        result = apply_expected(project, project.workspace, items)
        assert result["revision"] == before + 1
        assert {lesson["id"] for lesson in project.list_entities("task_lesson")} == {
            lesson["id"] for lesson in lessons
        }
        saved = read_expected(project)["items"]
        assert all(item["configuration"]["rules"][0]["penalty"] == 10 for item in saved)
        for item in saved:
            item["configuration"] = {"schema_version": 2, "default_policy": "inherit", "rules": []}
        apply_expected(project, project.workspace, saved)
        assert all(not item["configuration"]["rules"] for item in read_expected(project)["items"])
        assert (
            project.connection.execute(
                "SELECT count(*) FROM ai_documents WHERE kind='action'"
            ).fetchone()[0]
            == 2
        )


def test_stale_or_invalid_batch_never_writes(tmp_path):
    project, lessons = setup_project(tmp_path)
    with project:
        slot = project.list_entities("time_slot")[0]
        revision = project.revision
        items = [
            {"lesson_id": lesson["id"], "revision": revision, "configuration": configuration(slot)}
            for lesson in lessons
        ]
        items[-1]["revision"] -= 1
        with pytest.raises(ProjectError):
            apply_expected(project, project.workspace, items)
        items[-1]["revision"] = revision
        items[-1]["configuration"]["rules"][0]["template_id"] = "missing"
        with pytest.raises(ProjectError):
            apply_expected(project, project.workspace, items)
        assert project.revision == revision
        assert all(not item["configuration"]["rules"] for item in read_expected(project)["items"])


def test_hidden_day_is_rejected(tmp_path):
    project, lessons = setup_project(tmp_path)
    with project:
        slot = project.list_entities("time_slot")[0]
        project.save_entity(
            "bell_schedule",
            {
                "id": slot["bell_schedule_id"],
                "display_config": {
                    "enabled_weekdays": [day for day in range(1, 8) if day != slot["weekday"]]
                },
            },
            project.revision,
        )
        with pytest.raises(ProjectError, match="隐藏"):
            apply_expected(
                project,
                project.workspace,
                [
                    {
                        "lesson_id": lessons[0]["id"],
                        "revision": project.revision,
                        "configuration": configuration(slot),
                    }
                ],
            )


def test_web_scope_resolution_and_unknown_condition(tmp_path):
    from stt_desktop.agent.scope_search import prepare_scope, finish_scope

    project, lessons = setup_project(tmp_path)
    with project:
        prepared = prepare_scope(project, "第一课次")
        assert (
            prepared["providerRequest"]["tools"][0]["function"]["name"]
            == "resolve_constraint_scope"
        )
        proposal = {
            "scope_query": {"lesson_ordinals": [1]},
            "confidence": 0.95,
            "interpretation": "第一课次",
        }
        message = {"role": "assistant", "content": json.dumps(proposal)}
        result = finish_scope(project, prepared["searchId"], message)
        assert len(result["rows"]) == 1 and result["rows"][0]["ordinal"] == 1
        prepared = prepare_scope(project, "周三下午的课")
        proposal["scope_query"]["sql"] = "select *"
        with pytest.raises(ProjectError, match="不支持"):
            finish_scope(project, prepared["searchId"], {"content": json.dumps(proposal)})
        proposal.pop("scope_query")
        proposal["scope_query"] = {}
        proposal["confidence"] = 0.2
        with pytest.raises(ProjectError, match="不确定"):
            finish_scope(project, prepared["searchId"], {"content": json.dumps(proposal)})


def test_picker_keeps_original_template_and_styles():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    picker = (root / "apps/desktop/src/components/AiExpectedTimePicker.vue").read_text(
        encoding="utf-8"
    )
    source = (root / "apps/desktop/src/web-course-editor/CourseEditor.vue").read_text(
        encoding="utf-8"
    )
    fragment = picker.split('<div class="web-course-editor">', 1)[1].split("</div></Teleport>", 1)[
        0
    ]
    assert fragment in source
    assert "web-course-editor/web-course-editor.css" in picker
    assert "prepareCoursePreferredPicker" in (
        root / "scripts/course-editor-local-adapter.txt"
    ).read_text(encoding="utf-8")
