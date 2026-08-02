"""Execute ElvUI's hand-written logic under a real Lua 5.1 VM and assert behaviour.

The suite has no test runner and the game client is the only true runtime, so the
static checks in this folder cannot catch logic errors. This script loads the actual
source files into Lua 5.1 (the same version WoW 3.3.5a ships) via lupa and exercises
the two pieces of custom logic that are easy to get subtly wrong:

  1. ElvUI/Core/Core.lua      -- the shared-locale proxy behind E:SetActiveLocale
  2. ElvUI/Core/ConfigSearch  -- CS.Casefold, used by the /ec search box

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
# 2. Casefold
# ---------------------------------------------------------------------------
def test_casefold():
    print("\n=== CS.Casefold (ElvUI/Core/ConfigSearch.lua) ===")
    lua = LuaRuntime(encoding=None)  # raw bytes both ways, for exact UTF-8 semantics

    # Load the real UTF-8 library, which installs string.utf8lower.
    utf8_dir = os.path.join(ROOT, "ElvUI", "Libraries", "UTF8")
    for name, enc in (("utf8data.lua", "utf-8-sig"), ("utf8.lua", "utf-8")):
        with open(os.path.join(utf8_dir, name), encoding=enc) as fh:
            lua.execute(fh.read().encode("utf-8"))

    if not lua.eval(b"string.utf8lower ~= nil"):
        FAILURES.append("string.utf8lower was not installed by Libraries/UTF8")
        print("  [FAIL] string.utf8lower was not installed by Libraries/UTF8")
        return

    # Extract the real Casefold from ConfigSearch.lua rather than reimplementing it.
    cs_path = os.path.join(ROOT, "ElvUI", "Core", "ConfigSearch.lua")
    with open(cs_path, encoding="utf-8") as fh:
        src = fh.read()
    start = src.index("function CS.Casefold")
    end = src.index("\nend", start) + len("\nend")
    lua.execute(("CS = {}\nlocal utf8lower, type = string.utf8lower, type\n"
                 + src[start:end]).encode("utf-8"))
    fold = lua.eval(b"CS.Casefold")

    cases = [
        "ACTION BARS", "MiXeD Текст",                       # ascii + mixed
        "ДІЇ", "ПАНЕЛЬ ДІЙ", "ЄДНІСТЬ", "ЇЖА", "ҐАНОК",     # uk, incl. Є І Ї Ґ
        "ЁЖИК", "ЗДОРОВЬЕ",                                 # ru, incl. Ё
        "Здоров'я", "Bar 1: 50%", "[Test]",                 # punctuation/digits
    ]
    for text in cases:
        check(f"casefold({text!r})", fold(text.encode("utf-8")), text.lower())

    check("empty string", fold("".encode("utf-8")), "")
    check("idempotent on already-folded text", fold(fold("ДІЇ".encode("utf-8"))), "дії")

    # The guard clause in Casefold exists because utf8lower rejects non-strings.
    # Run pcall inside Lua and return just its success flag as a string, so the
    # result survives the Python boundary unambiguously.
    for arg in ("nil", "42"):
        outcome = lua.eval(
            b"(function() return tostring((pcall(string.utf8lower, %s))) end)()" % arg.encode()
        )
        check(f"utf8lower rejects {arg}, so Casefold's type guard is required", outcome, "false")
    check("Casefold itself tolerates nil via its guard", fold(None), "")


if __name__ == "__main__":
    test_locale_proxy()
    test_casefold()
    print(f"\n=== {PASSED} passed, {len(FAILURES)} failed ===")
    for name in FAILURES:
        print("  FAILED:", name)
    sys.exit(1 if FAILURES else 0)
