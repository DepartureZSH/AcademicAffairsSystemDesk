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
