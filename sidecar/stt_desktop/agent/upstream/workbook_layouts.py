"""Read-only compatibility for previously downloaded v2 workbooks."""
from datetime import time

from fastapi import HTTPException

LAYOUTS = {
    "timetable": ["周课表", "分日作息"],
    "planning": ["任课安排"],
    "constraints": ["排课规则"],
}
DAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
RULE_CHOICES = {"不要同时上课": "不重叠", "安排在同一时间开始": "同时开始", "安排在同一天": "同一天", "分散到不同天": "不同天", "使用同一间教室": "同一教室"}
PRIORITIES = {"高": 10, "中": 5, "低": 1}
PLAN_HEADERS = ["班级*", "科目*", "任课教师", "每周几节*", "每节多少分钟*", "上课教室"]
OVERRIDE_HEADERS = ["星期*", "第几节*", "开始时间*", "结束时间*"]
RULE_STARTS = range(4, 134, 13)


def read_layout(book, scene):
    """Return canonical sheet rows while preserving the visible source row."""
    cells_by_sheet = {}
    def fail(sheet, row, text):
        raise HTTPException(400, f"{sheet}第 {row} 行：{text}")

    def value(sheet, row, col):
        if sheet.title not in cells_by_sheet:
            cells_by_sheet[sheet.title] = list(sheet.iter_rows())
        rows = cells_by_sheet[sheet.title]
        if row > len(rows) or col > len(rows[row - 1]):
            return None
        cell = rows[row - 1][col - 1]
        raw = cell.value
        if cell.data_type == "f":
            fail(sheet.title, row, "不支持公式，请粘贴为值。")
        if isinstance(raw, time):
            if raw.second or raw.microsecond:
                fail(sheet.title, row, "时间请精确到分钟。")
            return raw.strftime("%H:%M")
        if isinstance(raw, str):
            raw = raw.strip()
        if len(str(raw or "")) > 2000:
            fail(sheet.title, row, "单元格内容过长。")
        return raw

    def present(values):
        return any(v not in (None, "") for v in values)

    def row(sheet, number, values):
        return {"row": number, "values": values, "source_sheet": sheet.title}

    def headers(sheet, number, expected):
        if [value(sheet, number, c) for c in range(1, len(expected) + 1)] != expected:
            fail(sheet.title, number, "表头已改变，请重新下载模板。")

    def bounds(sheet, max_row, max_col):
        if sheet.max_row > max_row or sheet.max_column > max_col:
            fail(sheet.title, max_row, "超出模板填写范围，请拆分文件；不要在表外添加内容。")

    if set(book.sheetnames) != {"填写说明", "_STT", "填写示例", *LAYOUTS[scene]}:
        raise HTTPException(400, "工作表名称不匹配，请不要增删或重命名工作表。")
    if scene == "planning":
        sheet = book["任课安排"]
        bounds(sheet, 2005, 6)
        headers(sheet, 5, PLAN_HEADERS)
        rows = []
        for r in range(6, sheet.max_row + 1):
            values = [value(sheet, r, c) for c in range(1, 7)]
            if present(values):
                home, subject, teacher, count, duration, room = values
                rows.append(row(sheet, r, [home, subject, count, duration, teacher, room]))
        return {"课程计划": rows}
    if scene == "constraints":
        sheet = book["排课规则"]
        bounds(sheet, 131, 6)
        rules, lessons = [], []
        for start in RULE_STARTS:
            headers(sheet, start + 4, ["班级*", "科目*", "任课教师", "本周第几节*"])
            name = value(sheet, start + 1, 2)
            requirement = value(sheet, start + 2, 2)
            strength = value(sheet, start + 2, 5)
            priority = value(sheet, start + 3, 2)
            entries = [(r, [value(sheet, r, c) for c in range(1, 5)]) for r in range(start + 5, start + 11)]
            for r in range(start + 5, start + 11):
                if present([value(sheet, r, 5), value(sheet, r, 6)]):
                    fail(sheet.title, r, "请只在班级、科目、任课教师、本周第几节四列中填写课程。")
            entries = [(r, v) for r, v in entries if present(v)]
            if not present([name, requirement, strength, priority]) and not entries:
                continue
            if requirement not in RULE_CHOICES:
                fail(sheet.title, start + 2, "请从下拉列表选择排课要求。")
            if strength not in {"必须满足", "尽量满足"}:
                fail(sheet.title, start + 2, "请选择必须满足或尽量满足。")
            if priority not in (None, "", *PRIORITIES):
                fail(sheet.title, start + 3, "优先级请选择高、中或低。")
            rules.append(row(sheet, start + 1, [name, RULE_CHOICES[requirement], "是" if strength == "必须满足" else "否", PRIORITIES[priority or "中"] if strength == "尽量满足" else None]))
            lessons.extend(row(sheet, r, [name, *v]) for r, v in entries)
        return {"规则": rules, "作用课次": lessons}
    sheet, daily = book["周课表"], book["分日作息"]
    bounds(sheet, 27, 10)
    bounds(daily, 2004, 4)
    headers(sheet, 7, ["节次", "开始时间", "结束时间", *DAYS])
    headers(daily, 4, OVERRIDE_HEADERS)
    name, mode, axis = value(sheet, 4, 2), value(sheet, 4, 8), value(sheet, 5, 2)
    schedules = [(r, [value(sheet, r, c) for c in range(2, 11)]) for r in range(8, 28)]
    for r in range(8, 28):
        if value(sheet, r, 1) != f"第 {r - 7} 节":
            fail(sheet.title, r, "请勿修改左侧节次编号。")
    schedules = [(r, v) for r, v in schedules if present(v)]
    overrides = {}
    for r in range(5, daily.max_row + 1):
        values = [value(daily, r, c) for c in range(1, 5)]
        if not present(values):
            continue
        day, ordinal, start, end = values
        if day not in DAYS or not str(ordinal).isdigit() or not 1 <= int(ordinal) <= 20 or not start or not end:
            fail(daily.title, r, "请填写星期、第几节（1 至 20）和完整起止时间。")
        key = (DAYS.index(day) + 1, int(ordinal))
        if key in overrides:
            fail(daily.title, r, "同一天同一节的时间重复，请合并。")
        overrides[key] = (start, end)
    if not schedules and not present([name, mode, axis]) and not overrides:
        return {"模板信息": [], "课次时段": []}
    days = [day for day in range(1, 8) if any(v[day + 1] not in (None, "") for _, v in schedules)]
    if not days:
        fail(sheet.title, 8, "请在需要上课的星期格填写上课或自定义内容。")
    if overrides and mode != "弹性时间":
        fail(daily.title, 5, "填写分日作息时，周课表的时间模式必须选弹性时间。")
    periods = []
    for r, values in schedules:
        start, end, *cells = values
        if not present(cells):
            fail(sheet.title, r, "填写时间后，请至少填写一个星期格。")
        for day in days:
            begin, finish = overrides.pop((day, r - 7), (start, end))
            content = cells[day - 1]
            cell_mode = "安排课次" if content == "上课" else "不安排" if content in (None, "", "不安排") else "自定义内容"
            periods.append(row(sheet, r, [name, day, r - 7, begin, finish, cell_mode, content if cell_mode == "自定义内容" else None]))
    if overrides:
        fail(daily.title, 5, "分日作息引用了周课表中未填写的星期或节次。")
    periods.sort(key=lambda item: (item["values"][1], item["values"][2]))
    return {"模板信息": [row(sheet, 4, [name, mode, ",".join(map(str, days)), axis])], "课次时段": periods}
