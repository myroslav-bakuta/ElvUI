"""Settings paths vs. defaults: every literal E.db / E.private / E.global key chain read in
the code should exist in the P / V / G defaults tables.

A miss is a typo (`E.private.tooltip.enabled` for `enable`), a setting with no default (it
reads nil, and a profile reset cannot restore it), or a dead setting. Defaults are taken
from every top-level `P.x = ...` / `V[...] = ...` / `G.x = ...` statement in the suite,
executed in Lua 5.1 (lupa), so plugin defaults spread over many files are included.

    python tools/analysis/db_defaults_check.py          # findings only, exit 1 if any
    python tools/analysis/db_defaults_check.py --all    # also the known, accepted misses
"""
import os, re, sys
import lupa.lua51 as lupa

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKIP_DIRS = {"Libraries", ".git", "graphify-out", "tools", "docs", ".claude", ".remember"}

# Misses that are expected: reading a setting to convert it (DBConversions), settings
# written at runtime, or tables created on demand. Prefix match on "kind.chain".
ACCEPTED = {
    # E:DBConversions (ElvUI/Core/Core.lua) and ElvUI_Enhanced conversions read old keys
    "db.auras.fontSize", "db.chat.panelColorConverted", "db.databars.experience.questXP.showBubbles",
    "db.general.vendorGrays", "db.unitframe.OORAlpha", "db.unitframe.colors.healthmultiplier",
    "db.unitframe.units.player.combatIcon", "db.unitframe.units.player.restIcon",
    "db.unitframe.units.player.combatfade", "db.enhanced.general.trainAllButton",
    "db.enhanced.nameplates.cacheUnitClass", "db.fogofwar", "db.general.minimap.buttons",
    "private.enhanced.blizzard", "private.enhanced.character.model", "private.skins.animations",
    "private.cooldown", "db.cooldown.useIndicatorColor", "db.unitframe.filters",
    # written at runtime, nil until then
    "db.LeftChatPanelFaded", "db.RightChatPanelFaded", "db.movers", "db.layoutSet", "db.hideTutorial",
    "private.install_complete", "global.aprilFools", "global.ignoreIncompatible",
    "private.enhanced.character.player.collapsedName2", "private.enhanced.character.player.orderName2",
    # one flag per supported addon / tweak, filled in by the plugin at load
    "private.addOnSkins", "private.CustomTweaks",
    # user-made filter tables (created by the options)
    "global.nameplates.filters", "global.nameplates.specialFilters", "global.unitframe.specialFilters",
    "global.unitframe.AuraBarColors", "global.unitframe.DebuffHighlightColors",
    "global.unitframe.aurafilters", "global.unitframe.buffwatch",
}

lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute(r"""
local stubmt = {}
stubmt.__index = function() return setmetatable({}, stubmt) end
stubmt.__call = function() return setmetatable({}, stubmt) end
stubmt.__concat = function() return "" end
for _, op in ipairs({"__add", "__sub", "__mul", "__div", "__unm", "__mod", "__pow"}) do
    stubmt[op] = function() return 0 end
end
setmetatable(_G, {__index = function() return setmetatable({}, stubmt) end})
E = setmetatable({media = {}, myclass = "WARRIOR", myrealm = "Realm", myname = "Name"}, stubmt)
L = setmetatable({}, {__index = function(_, k) return k end})

-- autovivify while loading, so P["A"]["B"] = {} works whatever order files define A in
local viv = {}
viv.__index = function(t, k) local v = setmetatable({}, viv) rawset(t, k, v) return v end
P, V, G = setmetatable({}, viv), setmetatable({}, viv), setmetatable({}, viv)

function Freeze(t, seen)
    seen = seen or {}
    if type(t) ~= "table" or seen[t] then return end
    seen[t] = true
    if getmetatable(t) == viv then setmetatable(t, nil) end
    for _, v in pairs(t) do Freeze(v, seen) end
end

function Exists(root, keys)
    local t = root
    for i = 1, #keys do
        if type(t) ~= "table" then return false, i - 1 end
        t = t[keys[i]]
        if t == nil then return false, i - 1 end
    end
    return true, #keys
end
""")
run_block = lua.eval("""function(src, name)
    local f, err = loadstring("local E, L, V, P, G = E, L, V, P, G\\n" .. src, name)
    if not f then return err end
    local ok, e = pcall(f)
    if not ok then return tostring(e) end
end""")

start_rx = re.compile(r"""^\s*(?:P|V|G)(?:\.[A-Za-z_]\w*|\[\s*"[^"]*"\s*\]|\[\s*'[^']*'\s*\])+\s*=(?!=)""")


def lua_files():
    for dp, dn, fns in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for fn in fns:
            if fn.endswith(".lua"):
                yield os.path.join(dp, fn)


def statements(text):
    """Top-level default assignments, with their table constructors, as source chunks."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if start_rx.match(lines[i]):
            j, depth = i, 0
            while j < len(lines):
                code = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|--.*$', "", lines[j])
                depth += code.count("{") - code.count("}")
                if depth <= 0:
                    break
                j += 1
            yield i + 1, "\n".join(lines[i:j + 1])
            i = j + 1
        else:
            i += 1


load_errors = []
sources = {}
for path in lua_files():
    text = open(path, encoding="utf-8-sig", errors="replace").read()
    sources[path] = text
    for ln, chunk in statements(text):
        err = run_block(chunk, f"{os.path.relpath(path, ROOT)}:{ln}")
        if err:
            load_errors.append(err)
g = lua.globals()
for t in (g.P, g.V, g.G):
    g.Freeze(t)
roots = {"db": g.P, "private": g.V, "global": g.G}

use_rx = re.compile(r"""\bE\.(db|private|global)((?:\.[A-Za-z_]\w*|\["[^"]+"\]|\['[^']+'\])+)""")
findings = {}
for path, text in sources.items():
    for ln, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("--"):
            continue
        for m in use_rx.finditer(line):
            kind, chain = m.groups()
            keys = [a or b or c for a, b, c in re.findall(r"""\.([A-Za-z_]\w*)|\["([^"]+)"\]|\['([^']+)'\]""", chain)]
            rest = line[m.end():]
            if rest[:1] in ("(", ":"):
                keys = keys[:-1]  # method call on the last part
            if not keys:
                continue
            ok, depth = g.Exists(roots[kind], lua.table_from(keys))
            if ok:
                continue
            if depth == len(keys) - 1 and re.match(r"\s*=[^=]", rest):
                continue  # assigning a new last key, e.g. a cache or a conversion target
            name = kind + "." + ".".join(keys[:depth + 1])
            findings.setdefault(name, []).append(f"{os.path.relpath(path, ROOT)}:{ln}")

show_all = "--all" in sys.argv
bad = 0
for name in sorted(findings):
    where = findings[name]
    accepted = any(name == a or name.startswith(a + ".") for a in ACCEPTED)
    if accepted and not show_all:
        continue
    bad += not accepted
    tag = "  (accepted)" if accepted else ""
    more = f" +{len(where) - 1}" if len(where) > 1 else ""
    print(f"E.{name}{tag}\n    {where[0]}{more}")

if load_errors:
    print(f"\n{len(load_errors)} default statement(s) could not run (stubs); first: {load_errors[0]}")
print(f"\n=== {bad} settings read without a default ===")
sys.exit(1 if bad else 0)
