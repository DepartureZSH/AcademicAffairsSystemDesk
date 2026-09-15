"""Regression contracts for the desktop-only web workflow adaptation."""
from pathlib import Path
import json
import re
from xml.etree.ElementTree import Element

import pytest

from PIL import Image
from stt_desktop.scheduling import SchedulingService
from stt_desktop.scheduler_engine.cgcs import SUPPORTED_DISTRIBUTIONS

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'apps/desktop/src'
COMMON_EXECUTABLE = ['NotOverlap', 'SameStart', 'SameTime', 'DifferentTime', 'Consecutive',
                     'Precedence', 'DifferentDays', 'SameDays', 'DifferentWeeks', 'SameRoom']


def test_ledger_does_not_expose_web_absent_fields():
    source = (SRC / 'components/SchoolDataView.vue').read_text(encoding='utf-8')
    template = source.split('<template>', 1)[1]
    assert '需要专用教室' not in template
    assert 'forms.subject.requires_special_room' not in template
    assert 'forms.teacher.status' not in template
    assert 'forms.room.status' not in template
    assert '>状态<' not in template
    # Keep compatibility values in the data model; do not delete existing data.
    assert 'requires_special_room: 0' in source


def test_project_context_strip_is_removed():
    source = (SRC / 'App.vue').read_text(encoding='utf-8')
    assert '返回工作台选择项目' not in source
    assert 'class="project-context"' not in source


def test_native_window_icon_matches_current_logo():
    with Image.open(ROOT / 'apps/desktop/public/app-icon.ico') as ico:
        frame = ico.ico.getimage(max(ico.ico.sizes(), key=lambda size: size[0]*size[1])).convert('RGBA')
        expected = frame.resize((32,32), Image.Resampling.LANCZOS).tobytes()
    assert (ROOT / 'apps/desktop/src-tauri/icons/taskbar-icon.rgba').read_bytes() == expected
    source = (ROOT / 'apps/desktop/src-tauri/src/lib.rs').read_text(encoding='utf-8')
    assert 'window.set_icon' in source
    assert 'include_bytes!("../icons/taskbar-icon.rgba")' in source


def test_common_rule_dialog_has_no_ai_or_backdrop_dismissal():
    source = (SRC / 'web-workflows/CommonConstraintDialog.vue').read_text(encoding='utf-8')
    assert 'ConstraintCategoryStrip' in source and 'ConstraintParameters' in source
    assert 'selectedRule.example' in source
    assert 'AI创建' not in source
    assert '@click.self=' not in source
    assert 'executable.has(selectedRule.value.type)' in source
    assert 'if (!canSave.value) return;' in source


def test_running_view_uses_web_cards_and_local_preflight():
    source = (SRC / 'components/SchedulingView.vue').read_text(encoding='utf-8')
    cards = (SRC / 'web-workflows/RunDashboardCards.vue').read_text(encoding='utf-8')
    for name in ['run-status-card','run-input-summary','run-result-card','validation-card']:
        assert name in cards
    assert "['选择算法', '检查数据', '确认排课']" in source
    assert 'localApi.runSchedulingRound' in source
    assert 'optimizationMode.value && selectedCandidateCanWarmStart.value' in source
    assert '@click.self=' not in source
    assert 'TimetableView' in source


@pytest.mark.parametrize('kind', COMMON_EXECUTABLE)
def test_selectable_common_rules_compile_into_local_solver_conditions(kind):
    source = (SRC / 'web-workflows/CommonConstraintDialog.vue').read_text(encoding='utf-8')
    enabled = re.search(r'const executable = new Set\(\[(.*?)\]\)', source).group(1)
    assert set(re.findall(r"'([^']+)'", enabled)) == set(COMMON_EXECUTABLE)
    assert kind in SUPPORTED_DISTRIBUTIONS
    distributions = Element('distributions')
    diagnostics = {'warnings': [], 'compiled_limit_count': 0}
    # This compiler method is pure: no project or filesystem state is accessed.
    compiler = object.__new__(SchedulingService)
    compiler._compile_user_constraints(distributions, Element('limits'), [{
        'id': 'ui-common-rule', 'name': '测试常见约束', 'type': kind,
        'severity': 'hard', 'weight': 100,
        'parameters': json.dumps({'lessonIds': ['second', 'first']}),
    }], {'task': ['first', 'second']}, {}, diagnostics)
    rule = distributions.find('distribution')
    assert rule is not None
    assert rule.attrib['type'] == kind
    assert rule.attrib['required'] == 'true'
    assert [child.attrib['id'] for child in rule.findall('class')] == ['second', 'first']
    assert diagnostics['warnings'] == []
