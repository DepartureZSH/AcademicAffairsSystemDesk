"""Local persistence adapter for the current web timetable editor.

The editor numbers periods from one. The local solver uses zero-based lesson slots,
not five-minute clock ticks. Layout metadata is retained without reinterpretation.
"""

from __future__ import annotations

import json
from typing import Any

from stt_desktop.storage import ProjectError, ProjectRepository
from stt_desktop.storage.project import utc_now, uuid7


def config(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        result = json.loads(value or "{}")
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError):
        return {}


class TimetableSettingsService:
    def __init__(self, project: ProjectRepository):
        self.project = project
        self.db = project.connection

    def read(self) -> dict[str, Any]:
        schedules = self.project.list_entities("bell_schedule")
        templates = []
        for row in schedules:
            display = config(row["display_config"])
            metadata = display.pop("_web_template", {})
            templates.append(
                {
                    **row,
                    **metadata,
                    "display_config": display,
                    "is_default": bool(row["is_default"]),
                    "slot_duration_minutes": metadata.get("slot_duration_minutes", 5),
                }
            )
        periods = []
        for row in self.project.list_entities("time_slot"):
            display = config(row["display_config"])
            editor_active = display.pop("_editor_active", bool(row["active"]))
            periods.append(
                {
                    **row,
                    "template_id": row["bell_schedule_id"],
                    "period_index": row["period_index"] + 1,
                    "active": editor_active,
                    "display_config": display,
                }
            )
        terms = self.project.list_entities("term")
        school: dict[str, Any] = {
            "active_term": next((t for t in terms if t["active"]), None),
            "weekly_timetable_templates": templates,
            "weekly_timetable_periods": periods,
            "default_weekly_timetable_template": next(
                (t for t in templates if t["is_default"]), None
            ),
        }
        for name, entity in {
            "teachers": "teacher",
            "rooms": "room",
            "room_types": "room_type",
            "subjects": "subject",
            "homerooms": "homeroom",
            "timetable_template_assignments": "timetable_template_assignment",
        }.items():
            school[name] = self.project.list_entities(entity)
        return {
            "schoolData": school,
            "project": self.project.project_info(),
            "revision": self.project.revision,
        }

    def save(self, data: dict[str, Any], expected_revision: int) -> dict[str, Any]:
        template = data.get("template")
        periods = data.get("periods")
        if not isinstance(template, dict) or not isinstance(periods, list):
            raise ProjectError("课表模板和节次格式不正确")
        name = str(template.get("name", "")).strip()
        if not name or len(name) > 200:
            raise ProjectError("模板名称须为 1–200 个字符")
        template_id = str(template.get("id") or uuid7())
        display = config(template.get("display_config"))
        metadata = {
            key: template.get(key)
            for key in (
                "template_kind",
                "period_source_template_id",
                "periods_locked",
                "slot_duration_minutes",
            )
        }
        source_id = metadata.get("period_source_template_id")
        self.project._begin_write(expected_revision)
        now = utc_now()
        try:
            existing = self.project.get_entity("bell_schedule", template_id)
            if source_id:
                source = self.project.get_entity("bell_schedule", str(source_id))
                if (
                    not source
                    or source_id == template_id
                    or config(source["display_config"])
                    .get("_web_template", {})
                    .get("period_source_template_id")
                ):
                    raise ProjectError("请选择一个独立的课表作为节次来源")
                metadata["periods_locked"] = True
                periods = self._source_periods(str(source_id))
            elif metadata.get("periods_locked"):
                raise ProjectError("复用节次时必须选择来源课表")
            display["_web_template"] = metadata
            is_default = bool(template.get("is_default"))
            if metadata.get("template_kind") == "special" and is_default:
                raise ProjectError("总课表不能设为默认作息模板")
            if (
                metadata.get("template_kind") != "special"
                and not self.db.execute(
                    "SELECT 1 FROM bell_schedules WHERE is_default = 1 AND id != ?", (template_id,)
                ).fetchone()
            ):
                is_default = True
            if is_default:
                self.db.execute(
                    "UPDATE bell_schedules SET is_default = 0 WHERE id != ?", (template_id,)
                )
            self.db.execute(
                """INSERT INTO bell_schedules
                (id, name, term_id, day_count, slot_duration_minutes, is_default, display_config, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, term_id=excluded.term_id,
                day_count=excluded.day_count, is_default=excluded.is_default,
                display_config=excluded.display_config, updated_at=excluded.updated_at""",
                (
                    template_id,
                    name,
                    template.get("term_id") or None,
                    int(template.get("day_count", 7)),
                    existing["slot_duration_minutes"] if existing else 40,
                    int(is_default),
                    json.dumps(display, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            self._write_periods(template_id, periods, display, now)
            # Reused templates keep their own stable slot IDs for existing constraints.
            for child in self.project.list_entities("bell_schedule"):
                child_display = config(child["display_config"])
                if (
                    child_display.get("_web_template", {}).get("period_source_template_id")
                    == template_id
                ):
                    self._write_periods(
                        child["id"], self._source_periods(template_id), child_display, now
                    )
            revision = self.project._commit_write(now)
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        self.project._write_manifest_revision(revision, now)
        return {"templateId": template_id, "revision": revision}

    def _source_periods(self, template_id: str) -> list[dict[str, Any]]:
        rows = self.project.list_entities("time_slot")
        return [
            {
                **row,
                "id": None,
                "period_index": row["period_index"] + 1,
                "active": config(row["display_config"]).get("_editor_active", bool(row["active"])),
            }
            for row in rows
            if row["bell_schedule_id"] == template_id
        ]

    def _write_periods(self, template_id: str, periods: list, display: dict, now: str) -> None:
        if len(periods) > 1400:
            raise ProjectError("模板节次数量过多")
        old = [
            row
            for row in self.project.list_entities("time_slot")
            if row["bell_schedule_id"] == template_id
        ]
        by_id = {row["id"]: row for row in old}
        by_position = {(row["weekday"], row["period_index"]): row for row in old}
        used: set[str] = set()
        positions: set[tuple[int, int]] = set()
        intervals: dict[int, list[tuple[int, int]]] = {}
        normalized = []
        enabled = display.get("enabled_weekdays", list(range(1, 8)))
        explicit_ids = {str(p.get("id")) for p in periods if isinstance(p, dict) and p.get("id")}
        for period in periods:
            if not isinstance(period, dict):
                raise ProjectError("节次数据格式不正确")
            try:
                day, index = int(period["weekday"]), int(period["period_index"]) - 1
                start, end = int(period["start_time_minutes"]), int(period["end_time_minutes"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ProjectError("请填写有效的节次和起止时间") from exc
            if not 1 <= day <= 7 or not 0 <= index < 200 or not 0 <= start < end <= 1440:
                raise ProjectError("节次或时间范围不正确，结束时间必须晚于开始时间")
            position = (day, index)
            if position in positions:
                raise ProjectError("同一天的节次序号不能重复")
            positions.add(position)
            previous = by_id.get(str(period.get("id")))
            if previous is None:
                at_position = by_position.get(position)
                if at_position and at_position["id"] not in explicit_ids:
                    previous = at_position
            slot_id = previous["id"] if previous else uuid7()
            if slot_id in used:
                raise ProjectError("同一个节次不能重复保存")
            used.add(slot_id)
            cell = config(period.get("display_config"))
            editor_active = bool(period.get("active", True))
            active = (
                editor_active
                and day in enabled
                and cell.get("cell_mode", "scheduled") == "scheduled"
            )
            if active:
                if any(start < b and end > a for a, b in intervals.setdefault(day, [])):
                    raise ProjectError(f"周{day}的上课时间有重叠，请检查起止时间")
                intervals[day].append((start, end))
            cell["_editor_active"] = editor_active
            normalized.append(
                (
                    slot_id,
                    template_id,
                    day,
                    index,
                    str(period.get("label", "")),
                    index,
                    1,
                    start,
                    end,
                    int(active),
                    json.dumps(cell, ensure_ascii=False),
                    previous["created_at"] if previous else now,
                    now,
                )
            )
        for slot in old:
            if slot["id"] not in used:
                if self.db.execute(
                    "SELECT 1 FROM availability_rules WHERE time_slot_id = ?", (slot["id"],)
                ).fetchone():
                    raise ProjectError("被约束配置引用的节次不能删除，请先调整相关约束")
                self.db.execute("DELETE FROM time_slots WHERE id = ?", (slot["id"],))
        # Temporarily vacate unique positions so moving rows doesn't collide.
        self.db.execute(
            "UPDATE time_slots SET period_index = period_index + 100000 WHERE bell_schedule_id = ?",
            (template_id,),
        )
        self.db.executemany(
            """INSERT INTO time_slots (id, bell_schedule_id, weekday, period_index, label,
            start_slot, length_slots, start_time_minutes, end_time_minutes, active,
            display_config, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET weekday=excluded.weekday, period_index=excluded.period_index,
            label=excluded.label, start_slot=excluded.start_slot, length_slots=excluded.length_slots,
            start_time_minutes=excluded.start_time_minutes, end_time_minutes=excluded.end_time_minutes,
            active=excluded.active, display_config=excluded.display_config, updated_at=excluded.updated_at""",
            normalized,
        )

    def delete(self, template_id: str, expected_revision: int) -> dict[str, int]:
        self.project._begin_write(expected_revision)
        now = utc_now()
        try:
            for row in self.project.list_entities("bell_schedule"):
                if (
                    config(row["display_config"])
                    .get("_web_template", {})
                    .get("period_source_template_id")
                    == template_id
                ):
                    raise ProjectError("其他课表正在复用此模板，请先调整它们的节次来源")
            if self.db.execute(
                "SELECT 1 FROM timetable_template_assignments WHERE bell_schedule_id = ?",
                (template_id,),
            ).fetchone():
                raise ProjectError("此模板已分配给学校数据，请先解除分配")
            if self.db.execute(
                """SELECT 1 FROM availability_rules WHERE bell_schedule_id = ?
                OR time_slot_id IN (SELECT id FROM time_slots WHERE bell_schedule_id = ?)""",
                (template_id, template_id),
            ).fetchone():
                raise ProjectError("此模板被约束配置引用，不能删除")
            self.db.execute("DELETE FROM bell_schedules WHERE id = ?", (template_id,))
            if not self.db.execute("SELECT 1 FROM bell_schedules WHERE is_default = 1").fetchone():
                for row in self.project.list_entities("bell_schedule"):
                    if (
                        config(row["display_config"]).get("_web_template", {}).get("template_kind")
                        != "special"
                    ):
                        self.db.execute(
                            "UPDATE bell_schedules SET is_default = 1 WHERE id = ?", (row["id"],)
                        )
                        break
            revision = self.project._commit_write(now)
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        self.project._write_manifest_revision(revision, now)
        return {"revision": revision}
