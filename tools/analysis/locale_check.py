"""Locale sanity: duplicate L["key"] assignments within one locale file
(later assignment silently overwrites the earlier — usually a copy-paste bug)."""
import os, re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (tools/<sub>/<script>)
rx = re.compile(r'^\s*L\[(["\'])(.+?)\1\]\s*=')

for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if not d.startswith('.')]
    if 'Locales' not in dirpath and 'locales' not in dirpath:
        continue
    for fn in filenames:
        if not fn.lower().endswith('.lua'):
            continue
        path = os.path.join(dirpath, fn)
        keys = Counter()
        first_line = {}
        vals = {}
        with open(path, encoding='utf-8', errors='replace') as f:
            for ln, line in enumerate(f, 1):
                m = rx.match(line)
                if m:
                    k = m.group(2)
                    keys[k] += 1
                    if k not in first_line:
                        first_line[k] = ln
                        vals[k] = line.strip()[:80]
        dups = {k: c for k, c in keys.items() if c > 1}
        if dups:
            rel = os.path.relpath(path, ROOT)
            print(f"{rel}: {len(dups)} duplicated keys")
            for k, c in sorted(dups.items(), key=lambda x: -x[1])[:15]:
                print(f"   x{c}  [{k!r}] first at line {first_line[k]}")
