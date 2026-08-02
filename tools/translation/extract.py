"""Extract ordered L[...] keys from each English locale file into JSON."""
import os, re, json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (tools/<sub>/<script>)
OUT = os.path.dirname(os.path.abspath(__file__))

FILES = {
    "elvui":   r"ElvUI\Locales\enUS.lua",
    "options": r"ElvUI_OptionsUI\Locales\enUS.lua",
    "enhanced":r"ElvUI_Enhanced\Locales\enUS.lua",
    "skins":   r"ElvUI_AddOnSkins\Locales\enUS.lua",
    "efl":     r"ElvUI_EnhancedFriendsList\Locales\English.lua",
    "micro":   r"ElvUI_MicrobarEnhancement\Locales\English.lua",
}

# match: L["..."] = ...   or   L['...'] = ...   capturing the key with original quote
rx = re.compile(r'^\s*L\[(?P<q>["\'])(?P<key>.*?)(?P=q)\]\s*=')

def unescape_lua(s, q):
    # We keep the RAW key text (as written in source) because the generated file
    # must reproduce it byte-for-byte. So we DON'T unescape; we store raw.
    return s

summary = {}
for name, rel in FILES.items():
    path = os.path.join(ROOT, rel)
    keys = []
    seen = set()
    with open(path, encoding='utf-8', errors='replace') as f:
        for ln, line in enumerate(f, 1):
            m = rx.match(line)
            if m:
                raw = m.group('key')
                q = m.group('q')
                if (raw, q) in seen:
                    continue
                seen.add((raw, q))
                keys.append({"raw": raw, "q": q})
    with open(os.path.join(OUT, f"keys_{name}.json"), "w", encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False, indent=0)
    summary[name] = len(keys)
    # also a plain list of decoded keys for reading/translation
    with open(os.path.join(OUT, f"keys_{name}.txt"), "w", encoding="utf-8") as f:
        for k in keys:
            f.write(k["raw"] + "\n")

print(json.dumps(summary, ensure_ascii=False, indent=2))
