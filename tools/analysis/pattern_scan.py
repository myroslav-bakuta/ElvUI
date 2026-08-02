"""Scan Lua sources for WoW 3.3.5 / Lua 5.1 incompatibilities and common problems.
Comments and string literals are stripped (with line numbers preserved) before scanning
so matches are real code."""
import os, re, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (tools/<sub>/<script>)
def strip_lua(src):
    """Replace comments and string contents with spaces, preserving newlines."""
    out = []
    i, n = 0, len(src)
    def long_bracket(j):
        # at src[j]=='[' check for [=*[
        k = j + 1
        eq = 0
        while k < n and src[k] == '=':
            eq += 1; k += 1
        if k < n and src[k] == '[':
            return eq, k + 1
        return None, None
    while i < n:
        c = src[i]
        if c == '-' and i + 1 < n and src[i+1] == '-':
            # comment
            eq, start = (None, None)
            if i + 2 < n and src[i+2] == '[':
                eq, start = long_bracket(i + 2)
            if eq is not None:
                close = ']' + '=' * eq + ']'
                end = src.find(close, start)
                end = (end + len(close)) if end != -1 else n
                out.append(''.join('\n' if ch == '\n' else ' ' for ch in src[i:end]))
                i = end
            else:
                end = src.find('\n', i)
                end = end if end != -1 else n
                out.append(' ' * (end - i))
                i = end
        elif c == '[':
            eq, start = long_bracket(i)
            if eq is not None:
                close = ']' + '=' * eq + ']'
                end = src.find(close, start)
                end = (end + len(close)) if end != -1 else n
                out.append('""' + ''.join('\n' if ch == '\n' else ' ' for ch in src[i+2:end]))
                i = end
            else:
                out.append(c); i += 1
        elif c in '"\'':
            q = c; j = i + 1
            while j < n:
                if src[j] == '\\':
                    j += 2; continue
                if src[j] == q or src[j] == '\n':
                    break
                j += 1
            out.append(q + ' ' * (j - i - 1) + (q if j < n and src[j] == q else ''))
            i = j + 1
        else:
            out.append(c); i += 1
    return ''.join(out)

CHECKS = [
    ("os./io./require (нема в WoW-сандбоксі)",
     re.compile(r'(?<![\w.:])(?:os\.\w+|io\.\w+|require\s*\(|dofile\s*\(|loadfile\s*\()')),
    ("Lua 5.2+ синтаксис/функції",
     re.compile(r'(?<![\w.:])(?:goto\s+\w|::\w+::|table\.pack\b|table\.unpack\b|rawlen\b|bit32\b)')),
    ("Retail-only WoW API",
     re.compile(r'(?<![\w.:])(?:C_[A-Z]\w+[.:]|GetSpecialization\s*\(|GetNumSpecializations\b|IsInRaid\s*\(|IsInGroup\s*\(|GetNumGroupMembers\b|UnitIsGroupLeader\b|PlaySoundKitID\b|GetItemInfoInstant\b|UnitAuraBySlot\b|C_Timer\b)')),
]

# top-level global assignment: col 0, `name =` (not ==, not local, no dot/colon/bracket)
GLOBAL_ASSIGN = re.compile(r'^([A-Za-z_]\w*)\s*=(?!=)')
GLOBAL_FUNC   = re.compile(r'^function\s+([A-Za-z_]\w*)\s*\(')
KNOWN_GLOBALS = {  # intentional globals in WoW addons
    'ElvUI', 'ElvDB', 'ElvPrivateDB', 'ElvCharacterDB', 'BINDING_HEADER_ELVUI',
    'SLASH_', 'StaticPopupDialogs',
}

def addon_of(rel):
    return rel.split(os.sep)[0]

results = defaultdict(list)          # checkname -> [(rel, line, text)]
globals_found = defaultdict(list)    # rel -> [(line, name)]

for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if not d.startswith('.')]
    for fn in filenames:
        if not fn.lower().endswith('.lua'):
            continue
        path = os.path.join(dirpath, fn)
        rel = os.path.relpath(path, ROOT)
        with open(path, encoding='utf-8', errors='replace') as f:
            src = f.read()
        code = strip_lua(src)
        lines = code.split('\n')
        orig_lines = src.split('\n')
        for name, rx in CHECKS:
            for ln, line in enumerate(lines, 1):
                m = rx.search(line)
                if m:
                    results[name].append((rel, ln, orig_lines[ln-1].strip()[:120]))
        # global leaks: only outside Libraries (libs define globals legitimately)
        if os.sep + 'Libraries' + os.sep not in path:
            for ln, line in enumerate(lines, 1):
                m = GLOBAL_ASSIGN.match(line) or GLOBAL_FUNC.match(line)
                if m:
                    nm = m.group(1)
                    if nm in ('local',) or any(nm.startswith(k) for k in KNOWN_GLOBALS):
                        continue
                    globals_found[rel].append((ln, nm, orig_lines[ln-1].strip()[:110]))

for name, hits in results.items():
    print(f"\n=== {name}: {len(hits)} hits ===")
    for rel, ln, text in hits[:60]:
        print(f"  {rel}:{ln}: {text}")
    if len(hits) > 60:
        print(f"  ... and {len(hits)-60} more")

print(f"\n=== TOP-LEVEL GLOBAL ASSIGNMENTS (poza Libraries): {sum(len(v) for v in globals_found.values())} ===")
for rel in sorted(globals_found):
    for ln, nm, text in globals_found[rel]:
        print(f"  {rel}:{ln}: {nm}  |  {text}")
