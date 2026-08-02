# tools/

Maintenance tooling for this ElvUI (WotLK 3.3.5a) suite. Pure Python 3 (tested on
3.13); the only third-party dependency is [`luaparser`](https://pypi.org/project/luaparser/)
(`pip install luaparser`), used by the syntax checker. Every script derives the repo
root from its own location, so just run them from anywhere:

```
python tools/analysis/syntax_check.py
python tools/translation/generate.py
```

---

## translation/ — Ukrainian (ukUA) localization

The suite ships English (`enUS`), Russian (`ruRU`) and Ukrainian (`ukUA`). The Ukrainian
files are **generated** from the English sources plus per-addon translation dictionaries,
so keys stay byte-exact and only the values are translated.

- **`generate.py`** — reads each addon's English locale line by line, keeps the exact
  `L["key"] =` prefix, and substitutes the Ukrainian value from the matching `tr_*.py`
  dict. It validates format-token (`%s`, `%d`, `%02x`) and WoW-markup (`|cff…|r`, `\n`,
  `[=[…]=]`) parity between English and Ukrainian and reports any mismatch. Untranslated
  keys are written as `= true` (which falls back to the English key at runtime).
- **`tr_elvui.py`, `tr_options.py`, `tr_enhanced.py`, `tr_skins.py`, `tr_efl.py`,
  `tr_micro.py`** — the translation dictionaries: `T = { "English source" : "Ukrainian" }`.
  Edit these to change wording, then re-run `generate.py` to rewrite the `ukUA.lua` files.
- **`extract.py`** — pulls the set of translatable keys out of the English sources
  (produces the `keys_*.txt` / `keys_*.json` reference dumps kept here).

Addons covered by the generator: `ElvUI`, `ElvUI_OptionsUI`, `ElvUI_Enhanced`,
`ElvUI_AddOnSkins`, `ElvUI_EnhancedFriendsList`, `ElvUI_MicrobarEnhancement`.

**Not covered:** `ElvUI_CustomTweaks` keeps all languages in one file
(`ElvUI_CustomTweaks/locales.lua`) — its Ukrainian block is maintained by hand there.

### How the whole UI gets one language

`ukUA` is **not** a real WoW 3.3.5a client locale, so `GetLocale()` never returns it.
Selecting it is wired up in three places:

1. `ElvUI_OptionsUI/General.lua` — the **Language** dropdown (`General > Language`),
   trimmed to English / Russian / Ukrainian.
2. `ElvUI/Core/Core.lua` — `ElvUI[2]` (the `L` table every module and plugin captures via
   `local E, L = unpack(ElvUI)`) is a **proxy** whose `__index` points at the active locale
   table. At file-load time SavedVariables aren't loaded yet, so it resolves to the client
   locale; `E:SetActiveLocale(...)`, called from `E:Initialize()` once the DB exists,
   re-points the proxy at the saved dropdown choice. Because every consumer holds the same
   proxy reference, one redirect switches the entire UI. (Safe because nothing iterates `L`.)
3. Every ukUA locale file registers into the **fork** app via
   `LibStub("AceLocale-3.0-ElvUI"):NewLocale("ElvUI", "ukUA")`, which is the registry
   `ElvUI[2]` reads from. Missing keys fall back to English automatically.

Plugins build their option pages lazily (via `EP:RegisterPlugin`, after login), so the
redirect reaches them. Any string captured at *file scope* keeps the client locale —
the one place that mattered, `ElvUI_CustomTweaks`, was moved into a deferred `GetTweaks()`.

---

## analysis/ — audit helpers

- **`syntax_check.py`** — parse every `.lua` with luaparser; report syntax errors and
  files carrying a UTF-8 BOM. (The only expected BOM is the vendored
  `ElvUI/Libraries/UTF8/utf8data.lua`.)
- **`check_load_case.py`** — verify every `.toc`/`.xml` `<Script>`/`<Include>` reference
  matches the on-disk file/dir case exactly. Passes on Windows regardless; run it before
  shipping to a case-sensitive (Linux) server.
- **`locale_check.py`** — cross-check locale key coverage between languages.
- **`analyze_toc.py`** — walk the `.toc` / `Load_*.xml` include chains and flag missing files.
- **`global_writes.py`** — flag accidental writes to Lua globals (missing `local`).
- **`onupdate_scan.py`** — find `OnUpdate` handlers lacking a throttle accumulator.
- **`pattern_scan.py`** — misc heuristic code-smell scan.
