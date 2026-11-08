"""Locale coverage: every literal L["..."] key used in the code must exist in enUS, ruRU
and ukUA.

The fork's AceLocale returns the key itself for a missing entry, so a gap shows English
(or a raw ID such as "TUTORIAL_TITLE47") in the ru/uk UI, and the config search cannot find
the option by its translated name. Keys are compared as decoded strings, so "a\\nb" in the
code matches a [=[a<newline>b]=] long-bracket key in a locale file.

    python tools/analysis/locale_coverage_check.py         # missing keys, exit 1 if any
    python tools/analysis/locale_coverage_check.py --all   # also list "= true" placeholders in ru/uk
"""
import os, re, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKIP_DIRS = {"Libraries", ".git", "graphify-out", "tools", "docs", ".claude", ".remember"}
LOCALES = ("enUS", "ruRU", "ukUA")

newloc_rx = re.compile(r'NewLocale\(\s*"([^"]+)"\s*,\s*"(\w{4})"')
# L["key"], L['key'] or L[ [=[key]=] ]
key_rx = re.compile(r'''L\[\s*(?:"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|\[(=*)\[(.*?)\]\3\])\s*\]''', re.S)
ESC = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'", "r": "\r"}


def decode(m):
    dq, sq, _, long_ = m.group(1), m.group(2), m.group(3), m.group(4)
    if long_ is not None:
        return long_[1:] if long_.startswith("\n") else long_
    raw = dq if dq is not None else sq
    return re.sub(r"\\(.)", lambda e: ESC.get(e.group(1), e.group(1)), raw)


def short(key):
    key = key.replace("\n", "\\n")
    return key if len(key) <= 90 else key[:87] + "..."


defs = defaultdict(dict)  # locale -> key -> "true" or "text"
uses = defaultdict(list)
for dp, dn, fns in os.walk(ROOT):
    dn[:] = [d for d in dn if d not in SKIP_DIRS]
    for fn in fns:
        if not fn.endswith(".lua"):
            continue
        path = os.path.join(dp, fn)
        text = open(path, encoding="utf-8-sig", errors="replace").read()
        blocks = list(newloc_rx.finditer(text))
        if blocks:
            for i, b in enumerate(blocks):
                loc = b.group(2)
                chunk = text[b.end(): blocks[i + 1].start() if i + 1 < len(blocks) else len(text)]
                for m in key_rx.finditer(chunk):
                    rhs = re.match(r"\s*=\s*(\S+)", chunk[m.end():])
                    if rhs:
                        defs[loc][decode(m)] = "true" if rhs.group(1).rstrip(";") == "true" else "text"
            continue
        for ln, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("--"):
                continue
            for m in key_rx.finditer(line):
                uses[decode(m)].append(f"{os.path.relpath(path, ROOT)}:{ln}")

missing_total = 0
for loc in LOCALES:
    missing = sorted(k for k in uses if k not in defs[loc])
    missing_total += len(missing)
    print(f"=== {loc}: {len(defs[loc])} keys, {len(missing)} used in code but missing")
    for k in missing:
        print(f"  {short(k)!r}  {uses[k][0]}")

if "--all" in sys.argv:
    for loc in LOCALES[1:]:
        placeholders = sorted(k for k, v in defs[loc].items() if v == "true" and k in uses)
        print(f"\n=== {loc}: {len(placeholders)} used keys left as '= true' (English shown)")
        for k in placeholders:
            print(f"  {short(k)!r}")

sys.exit(1 if missing_total else 0)
