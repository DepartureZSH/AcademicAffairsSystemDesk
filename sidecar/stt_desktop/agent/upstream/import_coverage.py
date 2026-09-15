"""Read-only coverage checks for complete lesson workbooks."""
from collections import Counter

from stt_desktop.agent.upstream.compiler import ActionCompilationError


def planning_manifest(attachments: list[dict]) -> list[dict]:
    expected = []
    for attachment in attachments:
        for sheet in (attachment.get("extracted_data") or {}).get("sheets", []):
            if sheet.get("truncated"):
                raise ActionCompilationError([{"code": "incomplete_import_source", "message": "附件工作表被截断，无法校验完整导入。"}])
            rows = sheet.get("rows") or []
            header = None
            for row in rows:
                values = [str(value or "").strip() for value in row.get("values", [])]
                if header is None:
                    if all(key in values for key in ("班级", "科目", "课次名")):
                        header = {key: values.index(key) for key in ("班级", "科目", "课次名")}
                    continue
                fields = [values[header[key]] if header[key] < len(values) else "" for key in ("班级", "科目", "课次名")]
                if not fields[2]:
                    continue
                if not all(fields):
                    raise ActionCompilationError([{"code": "incomplete_import_source", "message": f"附件{sheet.get('name')}第{row.get('row')}行缺少班级、科目或课次名，不能确认整份文件覆盖。"}])
                expected.append({"class": fields[0], "subject": fields[1], "lesson": fields[2], "row": row.get("row"), "sheet": sheet.get("name")})
    return expected


def validate_planning_coverage(manifest: list[dict], items: list[dict], school: dict, planning: dict) -> dict:
    expected = Counter((row["class"], row["subject"], row["lesson"]) for row in manifest)
    names = {key: {str(row["id"]): str(row.get("name") or "").strip() for row in school.get(key, [])} for key in ("homerooms", "subjects")}
    tasks = {str(task["id"]): dict(task) for task in planning.get("teaching_tasks", [])}
    for item in items:
        if item["target"] != "task":
            continue
        data = item.get("after_data") or item.get("before_data") or {}
        key = str(data.get("id") or item.get("entity_id") or item["id"])
        if item["operation"] == "delete":
            tasks.pop(key, None)
        elif item.get("after_data"):
            tasks[key] = item["after_data"]
    covered = Counter()
    for task in tasks.values():
        lessons = task.get("lessons")
        if not isinstance(lessons, list):
            lessons = [lesson for lesson in planning.get("task_lessons", []) if lesson.get("teaching_task_id") == task.get("id")]
        for lesson in lessons:
            if lesson.get("enabled") is False:
                continue
            covered[(names["homerooms"].get(str(task.get("homeroom_id")), ""), names["subjects"].get(str(task.get("subject_id")), ""), str(lesson.get("label") or lesson.get("name") or "").strip())] += 1
    missing = expected - covered
    report = {"expected_lessons": sum(expected.values()), "covered_lessons": sum(expected.values()) - sum(missing.values()),
              "expected_classes": len({key[0] for key in expected}), "missing_lessons": sum(missing.values()),
              "missing_classes": sorted({key[0] for key in missing})}
    if missing:
        raise ActionCompilationError([{"code": "incomplete_workbook_coverage", "message":
            f"完整附件覆盖校验未通过：共{report['expected_classes']}个班、{report['expected_lessons']}个课次，已有数据与本轮操作合计仅覆盖{report['covered_lessons']}个，仍缺{report['missing_lessons']}个。未生成可执行批次，请补齐后重新提交；缺失班级：{'、'.join(report['missing_classes'])}。",
            "coverage": report, "missing_samples": [{"class": key[0], "subject": key[1], "lesson": key[2], "count": count} for key, count in list(missing.items())[:20]]}])
    return report
