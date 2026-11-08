"""Scenario check for the nameplate class cache (ElvUI/Modules/Nameplates/Nameplates.lua).

Runs the real LoadClassCache / RememberClass / UnitClass source under Lua 5.1 (lupa)
with stubbed WoW globals: pruning of old entries, upgrade of undated entries, the
day stamp on a sighting, and no cache reads or writes in battlegrounds and arenas.

    python tools/analysis/npcache_check.py
"""
import os, sys
import lupa.lua51 as lupa

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "ElvUI", "Modules", "Nameplates", "Nameplates.lua")

text = open(SRC, encoding="utf-8").read()
start = text.index("local CLASS_CACHE_DAYS")
end = text.index('\telseif unitType == "ENEMY_PLAYER" then', start)
chunk = text[start:end] + "\tend\nend\n"

results = []
def check(name, cond):
    results.append((name, bool(cond)))

lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute(r"""
NOW = 20400 * 86400 + 3600
time = function() return NOW end
E = {myrealm = "Realm"}
NP = {}
RAID_CLASS_COLORS = {MAGE = {}, PRIEST = {}, WARRIOR = {}}
UNITCLASS = {}
UnitClass = function(unit) return "x", UNITCLASS[unit] end
function NP:GetUnitClassByGUID() return nil end
""")
prelude = "local floor, match, pairs, type, tonumber, select = math.floor, string.match, pairs, type, tonumber, select\n"
lua.execute(prelude + chunk)

lua.execute(r"""
ElvNPClassCache = {Realm = {
	Fresh = "MAGE:20390", Old = "PRIEST:20200", Legacy = "WARRIOR",
	Broken = "nonsense", Unknown = "DEMONHUNTER:20400",
}, Other = {Keep = "MAGE:1"}}
NP:LoadClassCache()
""")
g = lua.globals()
saved = g.ElvNPClassCache.Realm
check("fresh entry kept", saved.Fresh == "MAGE:20390" and g.NP.ClassCache.Fresh == "MAGE")
check("entry unseen for 200 days dropped", saved.Old is None and g.NP.ClassCache.Old is None)
check("undated entry upgraded to today", saved.Legacy == "WARRIOR:20400" and g.NP.ClassCache.Legacy == "WARRIOR")
check("malformed entry dropped", saved.Broken is None)
check("unknown class dropped", saved.Unknown is None)
check("other realms untouched", g.ElvNPClassCache.Other.Keep == "MAGE:1")

unitclass = lua.eval("function(name, unit) return NP:UnitClass({UnitName = name, unit = unit}, 'FRIENDLY_PLAYER') end")
lua.execute('UNITCLASS.party1 = "PRIEST"')
check("live class returned", unitclass("Newbie", "party1") == "PRIEST")
check("sighting stamped with today", saved.Newbie == "PRIEST:20400")
check("re-sighting refreshes the day", (unitclass("Fresh", "party1"), saved.Fresh)[1] == "PRIEST:20400")
check("cache answers without unit info", unitclass("Legacy", None) == "WARRIOR")
check("empty name never cached", (unitclass("", "party1"), saved[""])[1] is None)

lua.execute("NP.inPvP = true")
check("no cache read in pvp", unitclass("Legacy", None) is None)
lua.execute('UNITCLASS.raid5 = "MAGE"')
check("live class still works in pvp", unitclass("Stranger", "raid5") == "MAGE")
check("no cache write in pvp", saved.Stranger is None and g.NP.ClassCache.Stranger is None)

failed = 0
for name, ok in results:
    print(("  [PASS] " if ok else "  [FAIL] ") + name)
    failed += not ok
print(f"\n=== {len(results) - failed} passed, {failed} failed ===")
sys.exit(1 if failed else 0)
