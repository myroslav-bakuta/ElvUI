"""Verify every .toc / .xml <Script>/<Include> reference resolves with the EXACT
on-disk case. Windows is case-insensitive so mismatches load fine there, but a
Linux WoW-emu server (or a case-sensitive volume) will fail to load them.

Run:  python tools/analysis/check_load_case.py
Reports each reference whose case differs from the real file/dir on disk.
Virtual/Blizzard texture paths (Interface\\...) are ignored -- they aren't disk files.
"""
import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (tools/<sub>/<script>)

def real_full(dp, ref):
    comps = ref.replace("\\", "/").split("/")
    cur, out, bs = dp, [], "\\" in ref
    for part in comps:
        if part in ("", ".", ".."):
            out.append(part); cur = os.path.join(cur, part); continue
        try:
            names = [e.name for e in os.scandir(cur)]
        except OSError:
            return None
        real = part if part in names else next((n for n in names if n.lower() == part.lower()), None)
        if real is None:
            return None
        out.append(real); cur = os.path.join(cur, real)
    return ("\\" if bs else "/").join(out)

xml_re = re.compile(r'<(?:Script|Include)\s+file\s*=\s*"([^"]+)"', re.I)

def main():
    issues = 0
    for dp, dn, fn in os.walk(ROOT):
        if os.sep + "Libraries" in dp or os.sep + ".git" in dp:
            continue
        for f in fn:
            low, full, refs = f.lower(), os.path.join(dp, f), []
            if low.endswith(".toc"):
                for ln in open(full, encoding="utf-8", errors="replace"):
                    s = ln.strip().lstrip("﻿")
                    if s and not s.startswith("#"):
                        refs.append(s)
            elif low.endswith(".xml"):
                for m in xml_re.finditer(open(full, encoding="utf-8", errors="replace").read()):
                    refs.append(m.group(1))
            else:
                continue
            for ref in refs:
                rf = real_full(dp, ref)
                if rf is not None and rf != ref:
                    issues += 1
                    print(f"CASE  [{os.path.relpath(full, ROOT)}]  {ref}  ->  {rf}")
    print(f"\n=== load-chain case issues: {issues} ===")

if __name__ == "__main__":
    main()
