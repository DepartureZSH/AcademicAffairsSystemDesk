"""Extracted web conversation prompts and missing-action guards."""
import re
import json
from .tools import normalize_agent_scene
from .distributions import LABELS as ITC_DISTRIBUTION_LABELS
from .business_prompts import PLANNING_BUSINESS_PROMPT, CONVERSATION_BUSINESS_GUARD

def _scene_system_prompt(scene: str | None) -> str:
    scene = normalize_agent_scene(scene)
    policies = {
        "timetable": (
            "你正在课表设置现场。只处理课表模板自身的星期、时段、课次、表头和展示结构，"
            "只能生成课表模板的增删改查 Action。附件中的教师、班级和课程安排不是创建模板的前置条件。"
        ),
        "rooms": (
            "你正在教室设置现场。只提取教室类型和教室自身属性，只能生成教室类型和教室的增删改查 Action。"
            "附件中的课程、教师、课时和任课关系不是教室录入的前置条件。"
        ),
        "school": (
            "你正在学校数据现场。只提取学期、教师、班级和科目自身信息，只能生成这些对象的增删改查 Action。"
            "教师任课、班级科目、每周课时、教室安排等关系属于课程计划或授课任务，当前现场一律忽略，"
            "不得因此拒绝生成已能确定的基础数据 Action。附件是待导入数据源，即使数据库当前为 0 条，"
            "也应按名称去重并为可识别的教师、班级和科目分别生成 bulk_upsert。"
        ),
        "planning": (
            "你正在课程计划现场。课程计划只处理班级、科目和计划属性，授课任务处理教师、教室和课次。"
            "可查询学校、模板、课程计划、授课任务、课次偏好和约束，只能生成课程计划与授课任务 Action。"
            "必须优先查询真实 ID；只有此现场需要校验附件中的班级-科目-教师任课关系。"
        ),
        "constraints": (
            "你正在约束配置现场。只能生成约束 Action。必须查询真实授课任务、课次和已有约束，"
            "将自然语言或附件规则解析成引用真实课次 ID 的可执行 groups；不能用说明文字代替 Action。"
        ),
        "general": "你正在通用排课会话，可使用平台允许的全部查询和 Action。",
    }
    constraint_context = ""
    if scene in {"constraints", "general"}:
        constraint_context = (
            " 支持的 ITC2019 规则：" + "；".join(f"{key}={label}" for key, label in ITC_DISTRIBUTION_LABELS.items()) + "。"
            " 参数必须写在类型中：WorkDay(S)、MinGap(G)、MaxDays(D)、MaxDayLoad(S)、MaxBreaks(R,S)、MaxBlock(M,S)。"
            " 时间参数单位是5分钟，用户说40分钟应写8；D是星期数1到7，R是长课间次数。"
            " 例如每日总课长最多240分钟用MaxDayLoad(48)，两课间隔10分钟用MinGap(2)。"
            " 常用需求另有ParallelLimit(K)：同一实际日期和时刻，所选课次合计最多同时上K节，K为1到100的整数。"
            " 这是K个动态NotOverlap名额的组合，不是ITC2019原生类型；例如操场体育课同时最多4节用ParallelLimit(4)。"
            " 必须把共享名额的所有班级、科目的相关课次合并为一条约束，不能按授课任务拆分；不能生成全体两两NotOverlap，也不能改变实际教室。"
            " 分组创建时scenario_type用common:ParallelLimit(K)、group_by用all；直接创建时distribution_type用ParallelLimit(K)。"
            " SameStart只比较钟点；SameTime是时段包含；DifferentTime忽略星期和周比较时段是否重叠。"
            " SameDays和SameWeeks允许集合包含；DifferentDays和DifferentWeeks要求集合互斥。"
            " Precedence按给定课次顺序比较首次教学周、星期和结束/开始时间，不可排序打乱lesson_ids。"
            " MaxDays、MaxDayLoad、MaxBreaks、MaxBlock必须对整组课次设置一条约束，不可拆成两两约束。"
            " MaxBreaks只统计严格大于S的课间；MaxBlock将课间不超过S的课次合成块，单独长课不计超限。"
            " 缺少必要阈值时先向用户确认，不得自行假定分钟数或次数。"
        )
    business_context = PLANNING_BUSINESS_PROMPT if scene in {"planning", "general"} else ""
    return policies[scene] + constraint_context + business_context + CONVERSATION_BUSINESS_GUARD + " 不得借助自然语言绕过当前场景权限。"

def _scene_action_repair_prompt(scene: str, has_attachment: bool) -> str:
    attachment_rule = "附件中的结构化行是本轮待录入来源。" if has_attachment else "以用户指令和查询结果为准。"
    policies = {
        "timetable": "只生成 timetable_template Action；只校验模板结构本身，不等待学校数据或课程计划。",
        "rooms": "分别为可识别的 room_type 和 room 生成 Action；忽略任课、课程和课时信息。",
        "school": (
            "分别为可识别的 teacher、homeroom、subject 和 term 生成 Action。"
            "同一名称重复出现时去重；忽略任课关系、任课科目、任课班级和周课时，"
            "这些字段缺失或含义不明确不能阻止基础对象 Action。数据库为空意味着 create，不是信息不足。"
        ),
        "planning": (
            "只生成 course_plan 和 task Action。使用查询得到的真实班级、科目、教师 ID；"
            "无法唯一映射且影响用户要求时先追问，不得以补全操作为由绕过待回答问题或猜测字段。"
        ),
        "constraints": (
            "只生成 constraint Action。payload.groups 必须引用查询得到的真实课次 ID；"
            "无法形成真实分组时不制造占位 ID。"
        ),
        "general": "只生成当前允许且可由现有信息确定的 Action。",
    }
    business_context = PLANNING_BUSINESS_PROMPT if scene in {"planning", "general"} else ""
    return f"\n当前现场补充规则：{attachment_rule}{policies[scene]}{business_context}{CONVERSATION_BUSINESS_GUARD}"

def _extract_user_questions(content: str) -> tuple[str, list[str]]:
    patterns = [
        r"```user_questions\s*\n([\s\S]*?)```",
        r"user_questions[^\n]*\n\s*```(?:json)?\s*\n([\s\S]*?)```",
        r'user_questions\s*[:：]?\s*\n\s*(\[\s*"(?:\\.|[^"\\])*"(?:\s*,\s*"(?:\\.|[^"\\])*")*\s*\])',
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if not match:
            continue
        try:
            values = json.loads(match.group(1))
        except (ValueError, TypeError):
            values = None
        if isinstance(values, list) and values and all(isinstance(item, str) and item.strip() for item in values):
            return re.sub(pattern, "", content).strip(), [item.strip()[:1000] for item in values[:6]]
    # Older replies used numbered questions rather than structured metadata.
    questions = []
    if any(cue in content for cue in ("请回答", "请先回答", "请补充", "请确认", "需要确认", "需要您确认", "需要你确认")):
        for line in content.splitlines():
            if re.match(r"^\s*\d+[.、)]\s*", line) and ("？" in line or "?" in line):
                questions.append(re.sub(r"^\s*\d+[.、)]\s*", "", line).replace("**", "").strip()[:1000])
    return content, questions[:6]

def _requires_user_answers(content: str) -> bool:
    return bool(
        _extract_user_questions(content)[1]
        or "user_questions" in content
        or re.search(r"请(?:您)?确认[^\n]{0,160}后[^\n]{0,80}(?:再|将)生成", content)
    )

def _should_require_actions(content: str, attachment_ids: list[str], assistant_content: str) -> bool:
    if _requires_user_answers(assistant_content):
        return False
    text = str(content or "")
    write_words = (
        "新增", "添加", "删除", "更新", "导入", "插入", "同步", "创建", "批量", "清空", "重建",
        "填写", "填上", "绑定", "设置", "分配", "指定", "替换", "修改", "调整", "应用", "生成", "录入", "保存",
    )
    targets = ("教师", "班级", "科目", "教室", "课程", "课次", "约束", "模板", "学期", "排课")
    if not any(word in text for word in write_words):
        return _assistant_claims_action_created(assistant_content)
    if any(target in text for target in targets):
        return True
    return bool(attachment_ids)

def _assistant_claims_action_created(content: str) -> bool:
    text = str(content or "")
    claims = (
        "我已生成操作计划",
        "已生成待确认操作",
        "已准备好操作计划",
        "请确认后执行",
        "等待确认后执行",
    )
    return any(claim in text for claim in claims)
