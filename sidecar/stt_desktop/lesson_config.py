"""Versioned local lesson preferences, independent of remote services."""

import json
import re


def parse_lesson_config(raw) -> dict:
    config = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(config, dict) or set(config) - {"preferred_times", "room_mode", "room_ids"}:
        raise ValueError("课次设置格式无效")
    mode = config.get("room_mode", "default")
    rooms = config.get("room_ids", [])
    rules = config.get("preferred_times", [])
    if mode not in ("default", "custom") or not isinstance(rooms, list) or len(rooms) > 200:
        raise ValueError("课次教室设置无效")
    if any(not isinstance(item, str) or not item for item in rooms) or len(set(rooms)) != len(
        rooms
    ):
        raise ValueError("课次教室不能重复或为空")
    if not isinstance(rules, list) or len(rules) > 5000:
        raise ValueError("期望时间数量无效")
    seen = set()
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"time_slot_id", "week_bits", "penalty"}:
            raise ValueError("期望时间格式无效")
        if not isinstance(rule["time_slot_id"], str) or not rule["time_slot_id"]:
            raise ValueError("请选择有效课节")
        if (
            not isinstance(rule["week_bits"], str)
            or not re.fullmatch(r"[01]{1,60}", rule["week_bits"])
            or "1" not in rule["week_bits"]
        ):
            raise ValueError("期望时间至少选择一周")
        if type(rule["penalty"]) is not int or rule["penalty"] not in (-1, 0, 10, 30, 60):
            raise ValueError("候选优先级无效")
        key = (rule["time_slot_id"], rule["week_bits"])
        if key in seen:
            raise ValueError("同一周频率和课节只能设置一种优先级")
        seen.add(key)
    return {
        "room_mode": mode,
        "room_ids": rooms if mode == "custom" else [],
        "preferred_times": rules,
    }


def preferred_options(config: dict, slot_id: str, window_ids: set[str], week_bits: str):
    """Positive selections are alternatives; forbidden times always take precedence."""
    rules = config["preferred_times"]
    choices = [rule for rule in rules if rule["penalty"] >= 0]
    candidates = (
        [rule for rule in choices if rule["time_slot_id"] == slot_id]
        if choices
        else [{"week_bits": week_bits, "penalty": 0}]
    )
    options = {}
    for candidate in candidates:
        weeks = "".join(
            "1" if a == b == "1" else "0" for a, b in zip(week_bits, candidate["week_bits"])
        )
        if "1" not in weeks:
            continue
        if any(
            rule["penalty"] == -1
            and rule["time_slot_id"] in window_ids
            and any(a == b == "1" for a, b in zip(weeks, rule["week_bits"]))
            for rule in rules
        ):
            continue
        options[weeks] = min(options.get(weeks, 60), candidate["penalty"])
    return sorted(options.items())
