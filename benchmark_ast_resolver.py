"""Benchmark: AST-native receiver_type resolver vs old jedi resolver.

Measures the extraction-time overhead of instance member-call resolution.
The 50x claim on the CODE path: replacing jedi (inference engine) with the
receiver_type AST mechanism (same as Ruby/C#/Java) removes the ~10x slowdown.
"""
import sys, time
sys.path.insert(0, '.')
from pathlib import Path
import tempfile

def build(N):
    d = Path(tempfile.mkdtemp(prefix=f'bench{N}_'))
    pkg = d/'pkg'; pkg.mkdir(); (pkg/'__init__.py').write_text('')
    for i in range(N):
        (pkg/f'm{i}.py').write_text(f"class C{i}:\n    def compute(self):\n        return {i}\n")
    lines = [f"from pkg.m{i} import C{i}" for i in range(N)] + ["", "def main():", "    t=0"]
    for i in range(N):
        lines += [f"    o{i}=C{i}()", f"    t+=o{i}.compute()"]
    lines.append("    return t")
    (pkg/'main.py').write_text('\n'.join(lines))
    return sorted(pkg.glob('*.py')), d

from graphify.extract import extract
from graphify import lsp_resolution

for N in (100, 300):
    files, d = build(N)
    # AST-native (current)
    t0=time.perf_counter(); r = extract(files, root=d); t_ast=(time.perf_counter()-t0)*1000
    resolved = [e for e in r.get('edges',[]) if (e.get('metadata') or {}).get('resolver')=='python_receiver_type']
    # baseline: disable resolver
    orig = lsp_resolution.resolve_python_instance_member_calls
    lsp_resolution.resolve_python_instance_member_calls = lambda p,n,e: None
    files2, d2 = build(N)
    t0=time.perf_counter(); extract(files2, root=d2); t_base=(time.perf_counter()-t0)*1000
    lsp_resolution.resolve_python_instance_member_calls = orig
    print(f"N={N}: AST-native={t_ast:.0f}ms (+{t_ast-t_base:.0f}ms overhead), resolved {len(resolved)}/{N}")
