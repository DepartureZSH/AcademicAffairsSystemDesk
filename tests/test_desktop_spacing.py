from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_desktop_workflow_spacing_survives_web_resync():
    planning = (ROOT / 'apps/desktop/src/web-workflows/web-planning.css').read_text(encoding='utf-8')
    runs = (ROOT / 'apps/desktop/src/web-workflows/web-workflows.css').read_text(encoding='utf-8')
    for css, source in [(planning, 'web-planning-ui-overrides.css'), (runs, 'web-workflow-ui-overrides.css')]:
        overrides = (ROOT / 'scripts' / source).read_text(encoding='utf-8')
        assert css.endswith(overrides)
        assert 'font-size: 14px' in overrides
    assert 'section.web-planning.planning-guided-page { padding: 24px' in planning
    assert '.web-planning.planning-guided-page .planning-class-panel { padding: 20px' in planning
    assert '.desktop-runs-page .runs-dashboard > .run-card { padding: 20px' in runs
    assert '.desktop-runs-page .run-step strong { font-size: 12px' in runs
    template = (ROOT / 'apps/desktop/src/components/SchedulingView.vue').read_text(encoding='utf-8')
    assert 'class="web-workflow desktop-runs-page"' in template


def test_planning_toolbar_and_decorative_borders_survive_web_resync():
    css = (ROOT / 'apps/desktop/src/web-workflows/web-planning.css').read_text(encoding='utf-8')
    overrides = (ROOT / 'scripts/web-planning-ui-overrides.css').read_text(encoding='utf-8')
    assert css.endswith(overrides)
    for selector in [
        '.web-planning.planning-guided-page .planning-class-workbench',
        '.web-planning.planning-guided-page .official-flow-steps',
        '.web-planning.planning-guided-page .official-flow-steps > div',
        '.web-planning.planning-guided-page .official-flow-steps > div.active',
    ]:
        rule = overrides.split(selector + ' {', 1)[1].split('}', 1)[0]
        assert 'border: 0;' in rule
        assert 'box-shadow: none;' in rule
    toolbar = overrides.split('.web-planning .planning-filter-actions > button,', 1)[1].split('}', 1)[0]
    assert 'margin: 0;' in toolbar
    assert 'height: 40px;' in toolbar
    assert 'align-items: center;' in toolbar
    assert 'justify-content: center;' in toolbar
