"""Copy web distribution semantics while retaining desktop resource limits and warm starts."""
import ast
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root.parent / 'STT/apps/scheduler-engine/scheduler_engine'
target = root / 'sidecar/stt_desktop/scheduler_engine'


def imports(text):
    return text.replace('from xml_adapter.distributions import', 'from stt_desktop.agent.upstream.distributions import')


def transplant(filename, names):
    upstream = (source / filename).read_text(encoding='utf-8')
    local = (target / filename).read_text(encoding='utf-8')
    functions = {n.name: ast.get_source_segment(upstream, n) for n in ast.parse(upstream).body if isinstance(n, ast.FunctionDef)}
    nodes = {n.name: n for n in ast.parse(local).body if isinstance(n, ast.FunctionDef)}
    lines = local.splitlines(keepends=True)
    for name in sorted((n for n in names if n in nodes), key=lambda n: nodes[n].lineno, reverse=True):
        node = nodes[name]
        lines[node.lineno - 1:node.end_lineno] = [functions[name] + '\n']
    text = ''.join(lines)
    for name in names:
        if name not in nodes:
            text += '\n\n' + functions[name] + '\n'
    (target / filename).write_text(imports(text), encoding='utf-8')


transplant('cgcs.py', ['_blocking_class_ids','_is_feasible','_incremental_soft_penalty','_repair_group_integrity','_score','_placement','_is_group','_group_penalty','_violates'])
transplant('cp_sat.py', ['_compile_constraints','_compile_conflict_buckets','_distribution_signature'])
(target / 'distribution_groups.py').write_text(imports((source / 'distribution_groups.py').read_text(encoding='utf-8')), encoding='utf-8')
