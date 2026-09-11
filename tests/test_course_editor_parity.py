import hashlib
import json
from pathlib import Path

import pytest

from stt_desktop.lesson_planning import save_course_arrangement, set_course_scheduled
from stt_desktop.storage import ProjectError, RevisionConflictError
from test_lesson_planning import drafts_for, task_data, problem
from test_scheduling import seed_project

ROOT = Path(__file__).resolve().parents[1]


def test_course_dialog_template_provenance_and_components():
    folder = ROOT / 'apps/desktop/src/web-course-editor'
    provenance = json.loads((folder / 'provenance.json').read_text(encoding='utf-8'))
    source = (folder / 'CourseEditor.vue').read_text(encoding='utf-8')
    template = source.split('<template>\n', 1)[1].rsplit('\n</template>', 1)[0]
    assert hashlib.sha256(template.encode()).hexdigest() == provenance['templateSha256']
    for marker in ('<SearchableSelect', 'task-switcher-row', 'room-search-block',
                   'lesson-editor-sheet-mask', 'course-preferred-sheet-mask',
                   'course-candidate-row-heading', 'courseCandidateScale', 'guide-controls'):
        assert marker in source
    assert '连续节数' not in source and '完成并返回' not in source
    assert not (ROOT / 'apps/desktop/src/components/LessonEditor.vue').exists()
    css = (folder / 'web-course-editor.css').read_text(encoding='utf-8')
    for selector in ('.web-course-editor .lesson-editor-sheet-mask',
                     '.web-course-editor .course-preferred-sheet-mask',
                     '.web-course-editor .task-switcher-row'):
        assert selector in css
    assert 'z-index: 1600' in css and 'z-index: 1700' in css


def test_default_room_candidates_and_no_room_reach_solver(tmp_path):
    project, task, lessons = seed_project(tmp_path)
    with project:
        room, _ = project.save_entity('room', {'name':'第二教室'}, project.revision)
        other, _ = project.save_entity('room', {'name':'第一教室'}, project.revision)
        config = {'uses_rooms':True, 'room_ids':[other['id'], room['id']]}
        saved, _, _ = save_course_arrangement(project, {**task_data(task), 'planning_config':config}, drafts_for(lessons), project.revision)
        xml, _ = problem(project)
        assert {r.get('id') for r in xml.findall('classes/class/room')} == set(config['room_ids'])
        drafts = drafts_for(lessons)
        drafts[0]['planning_config'] = {'room_mode':'custom', 'room_ids':[room['id']]}
        saved, _, _ = save_course_arrangement(project, task_data(saved), drafts, project.revision)
        xml, _ = problem(project)
        assert [r.get('id') for r in xml.find('classes/class').findall('room')] == [room['id']]
        save_course_arrangement(project, {**task_data(saved), 'planning_config':{'uses_rooms':False,'room_ids':[]}}, drafts, project.revision)
        xml, _ = problem(project)
        assert not xml.findall('classes/class/room')


def test_not_scheduled_restore_and_revision_guard(tmp_path):
    project, task, lessons = seed_project(tmp_path)
    with project:
        args = (project, task['homeroom_id'], task['subject_id'], task['term_id'])
        revision = project.revision
        with pytest.raises(RevisionConflictError):
            set_course_scheduled(*args, False, revision - 1)
        project.save_entity('availability_rule', {'entity_type':'lesson','entity_id':lessons[0]['id']}, project.revision)
        set_course_scheduled(*args, False, project.revision)
        assert not project.list_entities('teaching_task') and not project.list_entities('task_lesson')
        assert not project.list_entities('availability_rule')
        assert project.list_entities('course_plan')[0]['weekly_slots'] == 0
        set_course_scheduled(*args, True, project.revision)
        assert project.list_entities('course_plan')[0]['weekly_slots'] == 1
        data = {**task_data(task)}
        data.pop('id')
        data.pop('course_plan_id', None)
        saved, _, _ = save_course_arrangement(project, data, [{**d, 'id':None} for d in drafts_for(lessons)], project.revision)
        assert saved['course_plan_id'] == project.list_entities('course_plan')[0]['id']
        assert project.list_entities('course_plan')[0]['weekly_slots'] == saved['weekly_slots']


def test_task_delete_and_not_scheduled_protect_constraints(tmp_path):
    project, task, lessons = seed_project(tmp_path)
    with project:
        project.save_entity('constraint', {'name':'引用课次','type':'SameDays','parameters':{'lesson_ids':[lessons[0]['id']]}}, project.revision)
        before = project.revision
        with pytest.raises(ProjectError, match='约束引用'):
            project.delete_entity('teaching_task', task['id'], before)
        with pytest.raises(ProjectError, match='约束引用'):
            set_course_scheduled(project,task['homeroom_id'],task['subject_id'],task['term_id'],False,before)
        assert project.revision == before and project.get_entity('teaching_task',task['id']) == task


@pytest.mark.parametrize('config', [{'uses_rooms':'false'}, {'uses_rooms':True,'room_ids':['x','x']}, {'uses_rooms':True,'unknown':1}])
def test_default_room_config_rejects_invalid_payloads(tmp_path, config):
    project, task, lessons = seed_project(tmp_path)
    with project:
        before = project.revision
        with pytest.raises(ProjectError):
            save_course_arrangement(project,{**task_data(task),'planning_config':config},drafts_for(lessons),before)
        with pytest.raises(ProjectError):
            project.save_entity('teaching_task',{'id':task['id'],'planning_config':config},before)
        assert project.revision == before
