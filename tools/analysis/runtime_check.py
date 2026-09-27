"""Execute ElvUI's hand-written logic under a real Lua 5.1 VM and assert behaviour.

The suite has no test runner and the game client is the only true runtime, so the
static checks in this folder cannot catch logic errors. This script loads the actual
source files into Lua 5.1 (the same version WoW 3.3.5a ships) via lupa and exercises
the two pieces of custom logic that are easy to get subtly wrong:

  1. ElvUI/Core/Core.lua      -- the shared-locale proxy behind E:SetActiveLocale
  2. ElvUI/Core/ConfigSearch  -- the /ec search box (delegates to search_check.py)

Requires: pip install lupa
Usage:    python tools/analysis/runtime_check.py
"""

import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    sys.exit("lupa with a Lua 5.1 binding is required: pip install lupa")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILURES = []
PASSED = 0


def check(label, got, want):
    global PASSED
    if isinstance(got, bytes):
        try:
            got = got.decode("utf-8")
        except UnicodeDecodeError:
            got = "<INVALID UTF-8: %r>" % list(got)
    ok = got == want
    if ok:
        PASSED += 1
    else:
        FAILURES.append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f"  got {got!r}, want {want!r}"))


# ---------------------------------------------------------------------------
# 1. Locale proxy
# ---------------------------------------------------------------------------
# ukUA is not a client locale, so GetLocale() never returns it. The proxy in
# Core.lua lets a saved-variable locale override reach every consumer that already
# captured L via `unpack(ElvUI)` at file scope, long before the DB was loaded.
def test_locale_proxy():
    print("=== locale proxy (ElvUI/Core/Core.lua) ===")
    lua = LuaRuntime()
    lua.execute(r"""
        local locales = {
          enUS = setmetatable({Hello="Hello"},  {__index=function(_,k) return k end}),
          ruRU = setmetatable({Hello="Privet"}, {__index=function(_,k) return k end}),
          ukUA = setmetatable({Hello="Pryvit"}, {__index=function(_,k) return k end}),
        }
        local ACL = {GetLocale = function(_, _, loc) return locales[loc] or locales.enUS end}
        ElvUI = {{Libs = {ACL = ACL}}, nil}
        local gameLocale = "ruRU"

        -- mirrors Core.lua
        ElvUI[2] = setmetatable({}, {__index = ACL:GetLocale("ElvUI", gameLocale)})
        ElvUI[1].SetActiveLocale = function(_, locale)
            local resolved = (locale and locale ~= "auto") and locale or gameLocale
            setmetatable(ElvUI[2], {__index = ACL:GetLocale("ElvUI", resolved)})
        end

        captured_L = ElvUI[2]  -- a plugin doing `local E, L = unpack(ElvUI)`
    """)

    check("resolves to client locale before any override", lua.eval("captured_L.Hello"), "Privet")

    lua.execute('ElvUI[1]:SetActiveLocale("ukUA")')
    check("override reaches a reference captured earlier", lua.eval("captured_L.Hello"), "Pryvit")
    check("table identity is preserved", lua.eval("captured_L == ElvUI[2]"), True)
    check("untranslated key falls back to the English key",
          lua.eval('captured_L["Some Untranslated Key"]'), "Some Untranslated Key")

    lua.execute('ElvUI[1]:SetActiveLocale("auto")')
    check('"auto" falls back to the client locale', lua.eval("captured_L.Hello"), "Privet")
    lua.execute("ElvUI[1]:SetActiveLocale(nil)")
    check("nil falls back to the client locale", lua.eval("captured_L.Hello"), "Privet")

    # The proxy holds no keys of its own; the redirect only works while that stays
    # true, since anything doing pairs(L) would silently see an empty table.
    check("proxy stores no keys directly (nothing may iterate L)",
          lua.eval("(function() local n=0 for _ in pairs(captured_L) do n=n+1 end return n end)()"), 0)


# ---------------------------------------------------------------------------
# 2. Config search
# ---------------------------------------------------------------------------
# Casefold, the match engine and the AceConfigDialog fork are driven end to end
# by search_check.py (it loads the real files into a WoW/AceGUI emulation).
def test_config_search():
    global PASSED
    print("\n=== /ec search (see search_check.py) ===")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import search_check
    passed, failed = search_check.run()
    PASSED += passed
    FAILURES.extend(failed)


if __name__ == "__main__":
    test_locale_proxy()
    test_config_search()
    print(f"\n=== {PASSED} passed, {len(FAILURES)} failed ===")
    for name in FAILURES:
        print("  FAILED:", name)
    sys.exit(1 if FAILURES else 0)
