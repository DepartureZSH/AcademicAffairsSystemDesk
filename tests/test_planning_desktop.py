from pathlib import Path
import sqlite3

import pytest
from stt_desktop.planning import copy_class_courses
from stt_desktop.storage import ProjectWorkspace, ProjectError, RevisionConflictError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def courses(tmp_path):
    with ProjectWorkspace(tmp_path).create_project('课程计划回归测试') as project:
        def save(kind, **data):
            return project.save_entity(kind, data, project.revision)[0]
        term = save('term', name='第一学期', week_count=21)
        source = save('homeroom', name='示范班', term_id=term['id'])
        target = save('homeroom', name='目标班', term_id=term['id'])
        teacher = save('teacher', name='教师')
        room = save('room', name='教室')
        subject = save('subject', name='数学')
        plan = save('course_plan', term_id=term['id'], homeroom_id=source['id'], subject_id=subject['id'], weekly_slots=5)
        task, lessons, _ = project.save_teaching_task_bundle(dict(term_id=term['id'],
            homeroom_id=source['id'], subject_id=subject['id'], course_plan_id=plan['id'],
            primary_teacher_id=teacher['id'], fixed_room_id=room['id'], weekly_slots=5,
            duration_slots=2, week_bits='1'*21, day_bits='11111'), project.revision)
        save('availability_rule', entity_type='lesson', entity_id=lessons[0]['id'],
             day_bits='10000', week_bits='1'*21, required=0, penalty=10)
        yield project, source, target, term, task


def test_class_copy_is_atomic_and_remaps_lessons(courses):
    project, source, target, term, original = courses
    before = project.revision
    counts, revision = copy_class_courses(project, source['id'], target['id'], term['id'], before)
    assert revision == before + 1
    assert counts == {'course_plan': 1, 'teaching_task': 1, 'task_lesson': 3, 'availability_rule': 1}
    copied = next(item for item in project.list_entities('teaching_task') if item['homeroom_id'] == target['id'])
    assert copied['primary_teacher_id'] is None and copied['fixed_room_id'] is None
    assert copied['course_plan_id'] != original['course_plan_id']
    copied_lessons = [item for item in project.list_entities('task_lesson') if item['teaching_task_id'] == copied['id']]
    assert [item['duration_slots'] for item in copied_lessons] == [2, 2, 1]
    assert all(item['week_bits'] == '1'*21 for item in copied_lessons)
    assert any(rule['entity_id'] == copied_lessons[0]['id'] for rule in project.list_entities('availability_rule'))
    assert project.get_entity('teaching_task', original['id']) == original
    assert project.integrity_check()['foreign_key_issues'] == []


def test_copy_does_not_overwrite_and_rejects_stale_revision(courses):
    project, source, target, term, _ = courses
    with pytest.raises(RevisionConflictError):
        copy_class_courses(project, source['id'], target['id'], term['id'], project.revision - 1)
    copy_class_courses(project, source['id'], target['id'], term['id'], project.revision)
    revision = project.revision
    with pytest.raises(ProjectError, match='不能覆盖'):
        copy_class_courses(project, source['id'], target['id'], term['id'], revision)
    assert project.revision == revision


def test_copy_rolls_back_failed_insert(courses, monkeypatch):
    project, source, target, term, _ = courses
    original_bulk = project.bulk_insert_entities
    def fail(batches, revision):
        batches['task_lesson'][0]['teaching_task_id'] = 'nonexistent'
        return original_bulk(batches, revision)
    monkeypatch.setattr(project, 'bulk_insert_entities', fail)
    before = project.revision
    with pytest.raises(sqlite3.IntegrityError):
        copy_class_courses(project, source['id'], target['id'], term['id'], before)
    assert project.revision == before
    assert not [task for task in project.list_entities('teaching_task') if task['homeroom_id'] == target['id']]
    assert not [plan for plan in project.list_entities('course_plan') if plan['homeroom_id'] == target['id']]


def test_missing_teacher_or_different_term_rejected(courses):
    project, source, target, term, task = courses
    project.save_entity('teaching_task', {'id': task['id'], 'primary_teacher_id': None}, project.revision)
    with pytest.raises(ProjectError, match='尚未完成'):
        copy_class_courses(project, source['id'], target['id'], term['id'], project.revision)
    other, _ = project.save_entity('term', {'name': '第二学期'}, project.revision)
    with pytest.raises(ProjectError, match='同一学期'):
        copy_class_courses(project, source['id'], target['id'], other['id'], project.revision)


def test_metadata_edit_preserves_lessons_and_allows_clear(courses):
    project, _, _, _, task = courses
    original_lessons = project.list_entities('task_lesson')
    original_rules = project.list_entities('availability_rule')
    saved, _ = project.save_entity('teaching_task', {'id': task['id'], 'primary_teacher_id': None,
                                                   'fixed_room_id': None}, project.revision)
    assert saved['primary_teacher_id'] is None and saved['fixed_room_id'] is None
    assert project.list_entities('task_lesson') == original_lessons
    assert project.list_entities('availability_rule') == original_rules


def test_latest_page_structure_and_safe_dialogs():
    source = (ROOT / 'apps/desktop/src/components/PlanningView.vue').read_text(encoding='utf-8')
    for marker in ('planning-class-page-heading', 'class-overview-filters', 'planning-filter-bar',
                   'class-planning-view-switch', 'class-planning-table', 'subject-editor-dialog',
                   'subject-import-card', 'localApi.copyClassCourses'):
        assert marker in source
    assert '@click.self' not in source
    assert 'aria-modal="true"' in source and "event.key !== 'Tab'" in source
    assert 'localApi.saveCourseArrangement' in (ROOT / 'apps/desktop/src/web-course-editor/useCourseEditor.ts').read_text(encoding='utf-8')
    assert "'1'.repeat(Number(term?.week_count" in source
    css = (ROOT / 'apps/desktop/src/web-workflows/web-planning.css').read_text(encoding='utf-8')
    assert 'repeat(auto-fill, minmax(min(240px, 100%), 1fr))' in css
    assert '.web-planning.planning-guided-page .planning-class-workbench' in css
