"""Local, revision-checked class course copying for the desktop planning page."""
from uuid import uuid4

from stt_desktop.storage import ProjectError, ProjectRepository, RevisionConflictError
from stt_desktop.storage.project import ENTITY_SPECS
from stt_desktop.lesson_config import parse_lesson_config


def copy_class_courses(project: ProjectRepository, source_id: str, target_id: str,
                       term_id: str, expected_revision: int) -> tuple[dict[str, int], int]:
    if project.revision != expected_revision:
        raise RevisionConflictError(expected_revision, project.revision)
    source = project.get_entity('homeroom', source_id)
    target = project.get_entity('homeroom', target_id)
    if not source or not target or source_id == target_id:
        raise ProjectError('请选择两个不同的有效班级')
    if not project.get_entity('term', term_id):
        raise ProjectError('请先设置有效学期')
    if any(item.get('term_id') and item['term_id'] != term_id for item in (source, target)):
        raise ProjectError('只能复制同一学期的班级课程')
    plans = project.list_entities('course_plan')
    tasks = project.list_entities('teaching_task')
    def in_term(item):
        return not item.get('term_id') or item['term_id'] == term_id
    if any(item['homeroom_id'] == target_id and in_term(item) for item in plans + tasks):
        raise ProjectError('目标班级已有课程配置，不能覆盖；请改选尚未配置的班级')
    source_tasks = [item for item in tasks if item['homeroom_id'] == source_id
                    and in_term(item) and item['status'] == 'active']
    source_task_ids = {item['id'] for item in source_tasks}
    source_lessons = [item for item in project.list_entities('task_lesson')
                      if item['teaching_task_id'] in source_task_ids]
    subjects = project.list_entities('subject')
    complete_subjects = {item['subject_id'] for item in source_tasks}
    if not subjects or any(item['id'] not in complete_subjects for item in subjects) or any(
        not item['primary_teacher_id'] or not any(
            lesson['teaching_task_id'] == item['id'] and lesson['enabled']
            for lesson in source_lessons) for item in source_tasks
    ):
        raise ProjectError('来源班级尚未完成全部科目的教师和课次配置')
    source_plans = [item for item in plans if item['homeroom_id'] == source_id and in_term(item)]
    plan_ids = {item['id']: str(uuid4()) for item in source_plans}
    task_ids = {item['id']: str(uuid4()) for item in source_tasks}
    lesson_ids = {item['id']: str(uuid4()) for item in source_lessons}

    def clone(kind, item, new_id, **changes):
        return {'id': new_id, **{key: item[key] for key in ENTITY_SPECS[kind].fields if key in item}, **changes}

    batches = {
        'course_plan': [clone('course_plan', item, plan_ids[item['id']], homeroom_id=target_id,
                              term_id=term_id) for item in source_plans],
        'teaching_task': [clone('teaching_task', item, task_ids[item['id']], homeroom_id=target_id,
                                term_id=term_id, course_plan_id=plan_ids.get(item['course_plan_id']),
                                primary_teacher_id=None, fixed_room_id=None) for item in source_tasks],
        'task_lesson': [clone('task_lesson', item, lesson_ids[item['id']],
                              teaching_task_id=task_ids[item['teaching_task_id']],
                              planning_config={**parse_lesson_config(item.get('planning_config', '{}')),
                                               'room_mode': 'default', 'room_ids': []},
                              source_id=lesson_ids[item['id']]) for item in source_lessons],
        'availability_rule': [clone('availability_rule', item, str(uuid4()),
                                    entity_id=lesson_ids[item['entity_id']])
                              for item in project.list_entities('availability_rule')
                              if item['entity_type'] == 'lesson' and item['entity_id'] in lesson_ids],
    }
    # Optimistic revision validation happens again inside the write transaction.
    return project.bulk_insert_entities(batches, expected_revision)
