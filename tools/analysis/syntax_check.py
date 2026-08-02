"""Parse every .lua file with luaparser; report syntax errors."""
import os, sys, concurrent.futures

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (tools/<sub>/<script>)
def collect():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for fn in filenames:
            if fn.lower().endswith('.lua'):
                files.append(os.path.join(dirpath, fn))
    return files

def check(path):
    from luaparser import ast
    bom = False
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            src = f.read()
        if src.startswith('﻿'):
            bom = True
            src = src.lstrip('﻿')
        ast.parse(src)
        return ('BOM', os.path.relpath(path, ROOT)) if bom else None
    except Exception as e:
        msg = str(e).split('\n')[0][:200].encode('ascii', 'replace').decode()
        return ('ERR', f"{os.path.relpath(path, ROOT)}: {msg}")

if __name__ == '__main__':
    files = collect()
    print(f"checking {len(files)} files...", flush=True)
    errors, boms = [], []
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as ex:
        for i, res in enumerate(ex.map(check, files, chunksize=4)):
            if res:
                (errors if res[0] == 'ERR' else boms).append(res[1])
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(files)} done, {len(errors)} errors", flush=True)
    print(f"\n=== SYNTAX ERRORS: {len(errors)} ===")
    for e in errors:
        print(e)
    print(f"\n=== FILES WITH UTF-8 BOM: {len(boms)} ===")
    for b in boms:
        print(b)
