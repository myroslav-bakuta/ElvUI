"""Find OnUpdate handlers that allocate per frame: table constructors, string concat,
closures, CreateFrame/format/gsub calls inside OnUpdate bodies."""
import os, concurrent.futures

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (tools/<sub>/<script>)
ALLOC_CALLS = {'CreateFrame', 'format', 'gsub', 'gmatch', 'strsplit', 'date', 'UnitAura'}

def line_of(node):
    ft = getattr(node, 'first_token', None)
    return ft.line if ft is not None else 0

def check(path):
    from luaparser import ast, astnodes
    rel = os.path.relpath(path, ROOT)
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            src = f.read().lstrip('﻿')
        tree = ast.parse(src)
    except Exception:
        return []

    local_funcs = {}
    for node in ast.walk(tree):
        if isinstance(node, astnodes.LocalFunction) and isinstance(node.name, astnodes.Name):
            local_funcs[node.name.id] = node
        elif isinstance(node, astnodes.LocalAssign):
            for tg, v in zip(node.targets, node.values or []):
                if isinstance(tg, astnodes.Name) and isinstance(v, astnodes.AnonymousFunction):
                    local_funcs[tg.id] = v

    results = []
    def audit(handler, where_line, label):
        stats = {'table': 0, 'concat': 0, 'closure': 0, 'calls': set()}
        for n in ast.walk(handler):
            if n is handler:
                continue
            if isinstance(n, astnodes.Table):
                stats['table'] += 1
            elif isinstance(n, astnodes.Concat):
                stats['concat'] += 1
            elif isinstance(n, astnodes.AnonymousFunction):
                stats['closure'] += 1
            elif isinstance(n, astnodes.Call) and isinstance(n.func, astnodes.Name):
                if n.func.id in ALLOC_CALLS:
                    stats['calls'].add(n.func.id)
            elif isinstance(n, astnodes.Invoke) and isinstance(n.func, astnodes.Name):
                pass
        if stats['table'] or stats['concat'] or stats['closure'] or stats['calls']:
            results.append((rel, where_line, label, stats['table'], stats['concat'],
                            stats['closure'], ','.join(sorted(stats['calls']))))

    for node in ast.walk(tree):
        if isinstance(node, astnodes.Invoke) and isinstance(node.func, astnodes.Name) \
           and node.func.id in ('SetScript', 'HookScript') and node.args:
            a0 = node.args[0]
            if isinstance(a0, astnodes.String) and a0.s in ('OnUpdate', b'OnUpdate') and len(node.args) > 1:
                h = node.args[1]
                if isinstance(h, astnodes.AnonymousFunction):
                    audit(h, line_of(node), 'inline')
                elif isinstance(h, astnodes.Name) and h.id in local_funcs:
                    audit(local_funcs[h.id], line_of(node), h.id)
    return results

def collect():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for fn in filenames:
            if fn.lower().endswith('.lua'):
                files.append(os.path.join(dirpath, fn))
    return files

if __name__ == '__main__':
    files = collect()
    allr = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as ex:
        for res in ex.map(check, files, chunksize=4):
            allr.extend(res)
    allr.sort(key=lambda x: -(x[3]*3 + x[4] + x[5]*3))
    print(f"=== OnUpdate handlers with per-frame allocations: {len(allr)} ===")
    print(f"{'file:line':70} {'handler':14} {'tbl':>3} {'..':>3} {'fn':>3}  calls")
    for rel, ln, label, t, c, cl, calls in allr:
        print(f"{rel+':'+str(ln):70} {label[:14]:14} {t:>3} {c:>3} {cl:>3}  {calls}")
