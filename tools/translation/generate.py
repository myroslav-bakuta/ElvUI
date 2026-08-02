"""Generate ukUA locale files from enUS sources + translation dicts.
Guarantees byte-exact keys (only the RHS value is replaced) and validates
format-token / WoW-markup parity between English and Ukrainian.
"""
import os, re, sys, importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (tools/<sub>/<script>)
SCR = os.path.dirname(os.path.abspath(__file__))

H_ELVUI = [
    "-- Ukrainian localization file for ukUA.",
    "local E = unpack(select(2, ...)); --Import: Engine, Locales, PrivateDB, ProfileDB, GlobalDB",
    'local L = E.Libs.ACL:NewLocale("ElvUI", "ukUA")',
    "",
]
H_OPTIONS = [
    "-- Ukrainian localization file for ukUA.",
    'local L = ElvUI[1].Libs.ACL:NewLocale("ElvUI", "ukUA")',
    "",
]
H_UNPACK = [
    "-- Ukrainian localization file for ukUA.",
    "local E = unpack(ElvUI); --Import: Engine, Locales, PrivateDB, ProfileDB, GlobalDB",
    'local L = E.Libs.ACL:NewLocale("ElvUI", "ukUA")',
    "",
]
H_LIBSTUB = [
    "-- Ukrainian localization file for ukUA.",
    'local AceLocale = LibStub:GetLibrary("AceLocale-3.0-ElvUI")',
    'local L = AceLocale:NewLocale("ElvUI", "ukUA")',
    "if not L then return end",
    "",
]

CONFIG = {
    "elvui":    dict(src=r"ElvUI\Locales\enUS.lua",                        dst=r"ElvUI\Locales\ukUA.lua",                        header=H_ELVUI,   tr="tr_elvui"),
    "options":  dict(src=r"ElvUI_OptionsUI\Locales\enUS.lua",             dst=r"ElvUI_OptionsUI\Locales\ukUA.lua",             header=H_OPTIONS, tr="tr_options"),
    "enhanced": dict(src=r"ElvUI_Enhanced\Locales\enUS.lua",              dst=r"ElvUI_Enhanced\Locales\ukUA.lua",              header=H_UNPACK,  tr="tr_enhanced"),
    "skins":    dict(src=r"ElvUI_AddOnSkins\Locales\enUS.lua",            dst=r"ElvUI_AddOnSkins\Locales\ukUA.lua",            header=H_UNPACK,  tr="tr_skins"),
    "efl":      dict(src=r"ElvUI_EnhancedFriendsList\Locales\English.lua",dst=r"ElvUI_EnhancedFriendsList\Locales\Ukrainian.lua",header=H_LIBSTUB,tr="tr_efl"),
    "micro":    dict(src=r"ElvUI_MicrobarEnhancement\Locales\English.lua",dst=r"ElvUI_MicrobarEnhancement\Locales\Ukrainian.lua",header=H_LIBSTUB,tr="tr_micro"),
}

LINE_RX = re.compile(r'^(?P<prefix>\s*L\[(?P<q>["\'])(?P<key>.*?)(?P=q)\]\s*=\s*)(?P<val>.*?)\s*$')
FMT_RX = re.compile(r'%%|%[-+ #0-9.]*[diouxXeEfgGqscApС]')  # note: tolerate a couple lookalikes

def load_tr(name):
    path = os.path.join(SCR, name + ".py")
    if not os.path.exists(path):
        return {}
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Normalise real newlines (from Python "\n") to the Lua escape "\n" (backslash+n)
    # in BOTH keys (so they match source keys, which store a literal backslash-n)
    # and values (so the generated Lua string stays on one line).
    norm = {}
    for k, v in mod.T.items():
        nk = k.replace('\r\n', '\n').replace('\n', '\\n')
        nv = v.replace('\r\n', '\n').replace('\n', '\\n')
        norm[nk] = nv
    extras = getattr(mod, "EXTRAS", "")
    return norm, extras

def lua_unescape(s):
    return (s.replace('\\"', '"').replace("\\'", "'"))

def lua_escape(s):
    # Only escape the closing-quote char; leave backslashes (so \n etc. survive).
    return s.replace('"', '\\"')

def fmt_tokens(s):
    toks = [t for t in FMT_RX.findall(s) if t != '%%']
    # normalise to just the conversion letter for a lenient multiset compare
    return sorted(re.sub(r'^%[-+ #0-9.]*', '%', t) for t in toks)

def markup_counts(s):
    return (
        s.count('|c'), s.count('|r'), s.count('|T'), s.count('|t'),
        s.count('|H'), s.count('|h'), s.count('|n'), s.count('\\n'),
    )

def english_display(raw_key, raw_val):
    v = raw_val.strip().rstrip(';').strip()
    if v == 'true':
        return lua_unescape(raw_key)
    m = re.match(r'^(["\'])(.*)\1$', v)
    if m:
        return lua_unescape(m.group(2))
    return lua_unescape(raw_key)  # fallback

def gen(name, cfg, strict=False):
    src = os.path.join(ROOT, cfg["src"])
    dst = os.path.join(ROOT, cfg["dst"])
    T, extras = load_tr(cfg["tr"])
    with open(src, encoding="utf-8", errors="replace") as f:
        raw = f.read().lstrip("﻿")
    lines = raw.replace("\r\n", "\n").split("\n")

    # find first L-line
    first = None
    for i, line in enumerate(lines):
        if LINE_RX.match(line):
            first = i
            break
    out = list(cfg["header"])
    total = translated = 0
    untr = []
    warn = []
    seen = set()
    body = lines[first:] if first is not None else []
    n = len(body)
    i = 0
    while i < n:
        line = body[i]
        m = LINE_RX.match(line)
        if not m:
            st = line.strip()
            if st == "" or st.startswith("--"):
                out.append(line)
            i += 1
            continue

        key = m.group("key")
        lookup = lua_unescape(key)
        val = m.group("val")

        # Multi-line long-bracket value: [[ ... ]] or [=[ ... ]=]
        span = 1
        lb = re.match(r'\[(=*)\[', val.strip())
        eng = None
        if lb:
            close = ']' + '=' * len(lb.group(1)) + ']'
            if close in val:
                inner = val.strip()
                inner = re.sub(r'^\[=*\[', '', inner)
                inner = re.sub(r'\]=*\]$', '', inner)
                eng = inner
            else:
                j = i + 1
                while j < n and close not in body[j]:
                    j += 1
                span = (j - i) + 1
                chunk = [re.sub(r'^.*?\[=*\[', '', body[i])] + body[i+1:j] + \
                        [re.sub(r'\]=*\].*$', '', body[j])] if j < n else body[i:j]
                eng = "\n".join(chunk)
        else:
            eng = english_display(key, val)

        if lookup in seen:
            i += span
            continue
        seen.add(lookup)
        total += 1

        uk = T.get(lookup)
        if uk is None:
            out.append(m.group("prefix") + "true")
            untr.append(lookup)
        else:
            if fmt_tokens(eng) != fmt_tokens(uk):
                warn.append((name, "FMT", lookup[:50], fmt_tokens(eng), fmt_tokens(uk)))
            if markup_counts(eng) != markup_counts(uk):
                warn.append((name, "MARKUP", lookup[:50], markup_counts(eng), markup_counts(uk)))
            out.append(m.group("prefix") + '"' + lua_escape(uk) + '"')
            translated += 1
        i += span

    # Manually-authored raw-Lua entries (e.g. long-bracket KEYS the parser can't
    # round-trip). Validate each declared source key really exists verbatim.
    if extras:
        src_norm = raw.replace("\r\n", "\n")
        for skey in re.findall(r'--@check:(.*)', extras):
            if skey and skey not in src_norm:
                warn.append((name, "EXTRA-KEY-MISSING", skey[:50], "", ""))
        clean = "\n".join(l for l in extras.split("\n") if not l.strip().startswith("--@check:"))
        out.append("")
        out.append(clean.strip("\n"))
        total += len(re.findall(r'--@check:', extras))
        translated += len(re.findall(r'--@check:', extras))

    # trailing newline
    text = "\n".join(out).rstrip("\n") + "\n"
    if not (strict and untr):
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return total, translated, untr, warn

if __name__ == "__main__":
    which = sys.argv[1:] or list(CONFIG)
    grand_untr = 0
    for name in which:
        total, translated, untr, warn = gen(name, CONFIG[name])
        print(f"[{name}] {translated}/{total} translated, {len(untr)} missing, {len(warn)} token-warnings")
        for w in warn[:40]:
            print("   WARN", w)
        if untr and len(untr) <= 60:
            for k in untr:
                print("   MISS", repr(k))
        grand_untr += len(untr)
    print(f"TOTAL missing: {grand_untr}")
