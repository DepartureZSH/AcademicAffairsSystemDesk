"""The assistant must retain the specialized web workflows, not just a chat box."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps/desktop/src/web-ai"


def test_all_specialized_components_and_styles_are_present():
    manifest = json.loads((WEB / "provenance.json").read_text(encoding="utf-8"))
    names = ["AgentView", "AgentConversation", "AgentActionChanges", "PlanningAiCreator",
             "TimetableAiCreator", "TimetableSheetAnnotator", "ConstraintAiCreator",
             "ConstraintAiWizard", "ConstraintTemplateGallery", "ConstraintExpansionStep"]
    for name in names:
        relative = f"components/{name}.vue"
        assert relative in manifest["files"]
        content = (WEB / relative).read_text(encoding="utf-8")
        assert "<template>" in content and "<style" in content
    page = (WEB / "components/AgentView.vue").read_text(encoding="utf-8")
    for name in ["PlanningAiCreator", "ConstraintAiCreator", "TimetableAiCreator", "AgentConversation"]:
        assert f"<{name}" in page
    assert '<slot name="notice">' in page  # Also visible inside fullscreen.
    assert (WEB / "styles/aiCreatorLayout.css").is_file()


def test_no_web_backend_or_web_quota_is_wired_to_desktop():
    page = (WEB / "components/AgentView.vue").read_text(encoding="utf-8")
    assert 'ref="tokenDetails"' not in page
    download = (WEB / "components/OfficialWorkbookButton.vue").read_text(encoding="utf-8")
    assert "await fetch" not in download
    adapter = (WEB / "useDesktopAgent.ts").read_text(encoding="utf-8")
    assert "expectedBaseUrl" in adapter and "confirmed:true" in adapter
    assert "所有修改先展示审核，确认后才写入本地项目" in adapter
    assert "ai_stream_complete" in adapter
    assert "fetch(" not in adapter
