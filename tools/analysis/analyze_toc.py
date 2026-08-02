"""Check .toc / .xml load chains: missing files, case mismatches, orphan lua files."""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (tools/<sub>/<script>)
ADDONS = [d for d in os.listdir(ROOT)
          if os.path.isdir(os.path.join(ROOT, d)) and not d.startswith('.')]

def real_case_exists(path):
    """Return (exists_insensitive, exact_case_match)."""
    if os.path.exists(path):
        # verify exact case component by component
        parts = []
        p = path
        while True:
            head, tail = os.path.split(p)
            if not tail:
                break
            parts.append(tail)
            p = head
        parts.reverse()
        cur = p  # drive root
        for part in parts:
            try:
                entries = os.listdir(cur if cur else '.')
            except OSError:
                return True, True
            if part in entries:
                cur = os.path.join(cur, part)
            else:
                # case-insensitive match?
                low = [e for e in entries if e.lower() == part.lower()]
                if low:
                    return True, False
                return True, True  # shouldn't happen
        return True, True
    return False, False

loaded = {}   # addon -> set of loaded files (normalized lower relative path)
problems = []

def load_xml(addon_root, xml_path, chain):
    rel = os.path.relpath(xml_path, addon_root).lower().replace('/', '\\')
    if rel in chain:
        problems.append(f"CYCLE: {xml_path}")
        return
    chain = chain | {rel}
    loaded_set = loaded[os.path.basename(addon_root)]
    loaded_set.add(rel)
    try:
        with open(xml_path, encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError as e:
        problems.append(f"UNREADABLE XML: {xml_path}: {e}")
        return
    # strip XML comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.S)
    for m in re.finditer(r'<(?:Script|Include)\s+file\s*=\s*(["\'])([^"\']+)\1', content, re.I):
        ref = m.group(2).replace('/', '\\')
        full = os.path.normpath(os.path.join(os.path.dirname(xml_path), ref))
        exists, exact = real_case_exists(full)
        if not exists:
            problems.append(f"MISSING (xml): {os.path.relpath(xml_path, ROOT)} -> {ref}")
            continue
        if not exact:
            problems.append(f"CASE MISMATCH (xml): {os.path.relpath(xml_path, ROOT)} -> {ref}")
        if full.lower().endswith('.xml'):
            load_xml(addon_root, full, chain)
        else:
            loaded_set.add(os.path.relpath(full, addon_root).lower().replace('/', '\\'))

for addon in ADDONS:
    addon_root = os.path.join(ROOT, addon)
    toc = os.path.join(addon_root, addon + '.toc')
    if not os.path.exists(toc):
        problems.append(f"NO TOC: {addon}")
        continue
    loaded[addon] = set()
    iface = None
    with open(toc, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip().lstrip('﻿')
            if line.startswith('##'):
                if line.lower().startswith('## interface:'):
                    iface = line.split(':', 1)[1].strip()
                continue
            if not line or line.startswith('#'):
                continue
            ref = line.replace('/', '\\')
            full = os.path.normpath(os.path.join(addon_root, ref))
            exists, exact = real_case_exists(full)
            if not exists:
                problems.append(f"MISSING (toc): {addon}.toc -> {ref}")
                continue
            if not exact:
                problems.append(f"CASE MISMATCH (toc): {addon}.toc -> {ref}")
            if full.lower().endswith('.xml'):
                load_xml(addon_root, full, set())
            else:
                loaded[addon].add(os.path.relpath(full, addon_root).lower().replace('/', '\\'))
    if iface != '30300':
        problems.append(f"INTERFACE: {addon}.toc has '## Interface: {iface}' (expected 30300)")

# orphan lua files (never referenced by any toc/xml chain)
print("=== LOAD-CHAIN PROBLEMS ===")
for p in problems:
    print(p)
print("\n=== ORPHAN LUA FILES (on disk but never loaded) ===")
for addon in sorted(loaded):
    addon_root = os.path.join(ROOT, addon)
    orphans = []
    for dirpath, dirnames, filenames in os.walk(addon_root):
        for fn in filenames:
            if not fn.lower().endswith('.lua'):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), addon_root).lower().replace('/', '\\')
            if rel not in loaded[addon] and fn.lower() != 'bindings.lua':
                orphans.append(rel)
    if orphans:
        print(f"[{addon}] ({len(orphans)}):")
        for o in sorted(orphans):
            print(f"  {o}")
