# ElvUI for WotLK 3.3.5a (fixes and localization)

A maintained copy of the ElvUI 6.09 suite for the Wrath of the Lich King 3.3.5a client, with bug fixes and a full Ukrainian translation. Done by Kappa.

## What's inside

**Localization.** English, Russian and Ukrainian across the whole suite, 1884 strings with full key parity between all three. The language is picked in the config under General > Language and applies to the entire UI, including plugins. Ukrainian is not a client locale, so it is served through a shared locale proxy that redirects after the saved variables load.

**Config search.** A search box in `/ec` that filters the options tree by name and description. Case insensitive for Latin and Cyrillic alike, it auto expands matching sections and highlights the parameters that matched.

**Bug fixes.**

* Nameplates: `r, g, b` leaked into the global namespace
* Reincarnation datatext: `OnUpdate` now throttles to once per second instead of running every frame
* DPS and HPS datatexts: skip combat log events that are not from the player or pet
* Duplicate locale keys in `ptBR.lua` and the options `enUS.lua`
* Config search case folding no longer depends on the C locale, which could corrupt Cyrillic text

## Addons

`ElvUI` is the core, everything else is a plugin that depends on it.

```
ElvUI                       ElvUI_EnhancedFriendsList
ElvUI_AddOnSkins            ElvUI_ExtraActionBars
ElvUI_AuraBarsMovers        ElvUI_MicrobarEnhancement
ElvUI_CustomTweaks          ElvUI_OptionsUI
ElvUI_Enhanced
```

## Installation

Copy the addon folders into `Interface\AddOns\` and restart the client. Requires a 3.3.5a client; these addons will not work on later versions.

## Development

There is no build or test step, the game client is the runtime. Use `/rl` in game to reload after a change. The `tools/` folder holds static analysis and translation scripts, see `tools/README.md`.

## Credits

ElvUI by Elv and Bunny, plus the respective authors of each plugin. Fixes and localization by Kappa.
