"""Guard desktop-specific UI fixes when re-extracting the web editor.

These source contracts supplement browser verification of actual computed
styles, radio selection, and backdrop clicks; they do not replace it.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "apps/desktop/src/web-timetable"


def test_editor_dialogs_require_explicit_close() -> None:
    view = (EDITOR / "TimetableSettingsView.vue").read_text(encoding="utf-8")
    assert '@click.self=' not in view
    for handler in (
        'cancelNewTimetableTemplate',
        'closeTemplateMarketplacePreview',
        'selectedPreviewCell = null',
    ):
        assert f'@click="{handler}"' in view


def test_local_style_overrides_survive_extraction() -> None:
    authored = (ROOT / "scripts/web-timetable-ui-overrides.css").read_text(encoding="utf-8")
    generated = (EDITOR / "web-timetable.css").read_text(encoding="utf-8")
    assert generated.endswith(authored)
    assert 'input[type="radio"]' in authored
    assert 'appearance: auto' in authored
    assert 'font-size: 14px' in authored
    assert 'text-align: inherit' in authored


def test_planning_choices_remain_mutually_exclusive_and_disable_reuse() -> None:
    component = (EDITOR / "TemplatePlanningMode.vue").read_text(encoding="utf-8")
    assert component.count('type="radio"') == 2
    assert component.count('name="template-planning-mode"') == 2
    assert ':disabled="disabled || !canReuse"' in component


def test_timetable_editor_uses_full_content_width() -> None:
    authored = (ROOT / "scripts/web-timetable-ui-overrides.css").read_text(encoding="utf-8")
    rule = authored.split('.web-timetable .timetable-settings-layout {', 1)[1].split('}', 1)[0]
    assert 'grid-template-columns: minmax(0, 1fr);' in rule
    assert 'min-width: 0;' in rule
