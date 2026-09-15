"""Extract pure web conversation guards without the cloud service dependencies."""
import ast
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root.parent / 'STT/apps/api/app/agent/service.py').read_text(encoding='utf-8')
names = {'_scene_system_prompt', '_scene_action_repair_prompt', '_extract_user_questions', '_requires_user_answers', '_should_require_actions', '_assistant_claims_action_created'}
functions = [ast.get_source_segment(source, node) for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(functions) == len(names)
text = '"""Extracted web conversation prompts and missing-action guards."""\nimport re\nimport json\nfrom .tools import normalize_agent_scene\nfrom .distributions import LABELS as ITC_DISTRIBUTION_LABELS\nfrom .business_prompts import PLANNING_BUSINESS_PROMPT, CONVERSATION_BUSINESS_GUARD\n\n'
(root / 'sidecar/stt_desktop/agent/upstream/conversation_guards.py').write_text(text + '\n\n'.join(functions) + '\n', encoding='utf-8')
